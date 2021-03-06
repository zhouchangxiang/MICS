import redis
from flask import Blueprint, render_template, request, make_response, send_file, jsonify
import json
import datetime
from sqlalchemy import desc
from dbset.database.db_operate import db_session, pool
from dbset.main.BSFramwork import AlchemyEncoder
from flask_login import login_required, logout_user, login_user, current_user, LoginManager
import calendar

from handlers.energymanager.energy_manager import energyStatistics, energyStatisticsCost, energyStatisticshour
from models.SystemManagement.core import RedisKey, ElectricEnergy, WaterEnergy, SteamEnergy, LimitTable, Equipment, \
    AreaTable, Unit, TagClassType, TagDetail, BatchMaintain
from models.SystemManagement.system import EarlyWarning, EarlyWarningLimitMaintain, WaterSteamBatchMaintain, \
    AreaTimeEnergyColour, ElectricProportion, IncrementElectricTable, ElectricPrice, RatedPowerMaintain, ElectricSiteURL
from tools.common import insert, delete, update
from dbset.database import constant
from dbset.log.BK2TLogger import logger, insertSyslog
import datetime
import arrow
import time
import numpy as np
import pandas as pd
from io import BytesIO
from flask import Flask, send_file, make_response

energyElectric = Blueprint('energyElectric', __name__, template_folder='templates')

arro = arrow.now()
pool = redis.ConnectionPool(host=constant.REDIS_HOST)
redis_conn = redis.Redis(connection_pool=pool)

from datetime import timedelta


def getWeekDaysByNum(m, n):  # 获取第几周到第几周每周的第一天和最后一天
    # 当前日期
    now = datetime.now().date()
    dayDict = {}
    for x in range(m, n + 1):
        # 前几周
        if x < 0:
            lDay = now - timedelta(days=now.weekday() + (7 * abs(x)))
        # 本周
        elif x == 0:
            lDay = now - timedelta(days=now.weekday())
        # 后几周
        else:
            lDay = now + timedelta(days=(7 - now.weekday()) + 7 * (x - 1))
        rDay = lDay + timedelta(days=6)
        dayDict[x] = [str(lDay), str(rDay)]
    return dayDict


def getMonthFirstDayAndLastDay(year, month):
    """
    :param year: 年份，默认是本年，可传int或str类型
    :param month: 月份，默认是本月，可传int或str类型
    :return: firstDay: 当月的第一天，datetime.date类型
              lastDay: 当月的最后一天，datetime.date类型
    """
    if year:
        year = int(year)
    else:
        year = datetime.date.today().year

    if month:
        month = int(month)
    else:
        month = datetime.date.today().month

    # 获取当月第一天的星期和当月的总天数
    firstDayWeekDay, monthRange = calendar.monthrange(year, month)

    # 获取当月的第一天
    firstDay = datetime.date(year=year, month=month, day=1)
    lastDay = datetime.date(year=year, month=month, day=monthRange)
    return firstDay, lastDay


def addzero(j):
    if j < 10:
        return "0" + str(j)
    else:
        return str(j)


def accumulation(EnergyValues):
    eleY = 0.0
    for EnergyValue in EnergyValues:
        eleY = eleY + float(EnergyValue[0])
    return eleY


def strlastMonth(currmonth):
    curr = currmonth.split("-")
    str0 = curr[0]
    str1 = curr[1]
    if "0" in str1:
        str00 = str1[1]
    else:
        str00 = str1
    if str00 == "1":
        return str(int(str0) - 1) + "-" + "12"
    else:
        las = int(str00) - 1
        if las < 10:
            la = "0" + str(las)
        else:
            la = str(las)
        return str0 + "-" + la


def energyElectricSelect(data):
    if request.method == 'GET':
        try:
            dir = {}
            data = request.values
            Area = data.get("Area")
            StartTime = data.get("StartTime")
            EndTime = data.get("EndTime")
            energy = "电"
            elecount = 0.0
            if Area is not None and Area != "":
                oclass = db_session.query(TagDetail).filter(TagDetail.EnergyClass == energy,
                                                            TagDetail.AreaName == Area).all()
            else:
                oclass = db_session.query(TagDetail).filter(TagDetail.EnergyClass == energy).all()
            oc_list = []
            for oc in oclass:
                # if oc.TagClassValue not in ['E_Area_ZH_50_1_41_3', 'E_Area_YTQ_38_2_29_3', 'E_Area_GT_30_2_19_2', 'E_Area_TQR_18_2_36_4']:
                #     oc_list.append(oc.TagClassValue)
                # else:
                #     pass
                oc_list.append(oc.TagClassValue)
            if len(oc_list) > 0:
                elecount = energyStatistics(oc_list, StartTime, EndTime, energy)
            else:
                elecount = 0.0
            dir["value"] = elecount
            dir["type"] = "电"
            unit = db_session.query(Unit.UnitValue).filter(Unit.UnitName == energy).first()[0]
            dir["unit"] = unit
            # 成本
            if len(oc_list) > 0:
                cost = energyStatisticsCost(oc_list, StartTime, EndTime, energy)
            else:
                cost = 0.0
            dir["cost"] = cost
            return json.dumps(dir, cls=AlchemyEncoder, ensure_ascii=False)
        except Exception as e:
            print(e)
            insertSyslog("error", "能耗查询报错Error：" + str(e), current_user.Name)
            return json.dumps([{"status": "Error：" + str(e)}], cls=AlchemyEncoder, ensure_ascii=False)


@energyElectric.route('/electric_report', methods=['GET'])
def get_electric():
    """
    获取电报表的数据接口
    """
    try:
        start_time = request.values.get('start_time')
        end_time = request.values.get('end_time')
        # 当前页数
        current_page = int(request.values.get('offset'))
        # 每页显示条数
        pagesize = int(request.values.get('limit'))
        area_name = request.values.get('area_name')
        if area_name:
            rows = 'select top ' + str(pagesize) + ' CalculationID,TagClassValue,AreaName,IncremenValue,CollectionDate ' + \
                   'from [DB_MICS].[dbo].[IncrementElectricTable] where ID not in ' + '(select top ' + str(
                (current_page - 1) * pagesize) + \
                   ' ID from [DB_MICS].[dbo].[IncrementElectricTable] where cast(IncremenValue as float) != 0.0 ' + \
                   'and AreaName=' + "'" + area_name + "'" + ' and CollectionDate between ' + "'" + start_time + "'" + \
                   " and " + "'" + end_time + "'" + ' order by CollectionDate asc, ID asc)' + 'and AreaName=' + "'" + \
                   area_name + "'" + 'and cast(IncremenValue as float) != 0.0 and CollectionDate between ' + "'" + \
                   start_time + "'" + " and " + "'" + end_time + "'" + ' order by CollectionDate asc, ID asc'
            result3 = db_session.execute(rows).fetchall()
            total = 'select count(ID) as total from [DB_MICS].[dbo].[IncrementElectricTable] where cast(IncremenValue as' \
                    ' float) != 0.0 and AreaName=' + "'" + area_name + "'" + ' and CollectionDate between ' + "'" + \
                    start_time + "'" + " and" + "'" + end_time + "'"
            result2 = db_session.execute(total).fetchall()
            tag_list = db_session.query(TagDetail).filter(TagDetail.AreaName == area_name,
                                                          TagDetail.EnergyClass == '电').all()
            tag_point = [index.TagClassValue for index in tag_list]
            data = []
            for item in result3:
                query_electric = db_session.query(ElectricEnergy).filter(ElectricEnergy.ID == item.CalculationID).first()
                query_tagdetai = db_session.query(TagDetail).filter(TagDetail.TagClassValue == item.TagClassValue).first()
                tag_area = query_tagdetai.FEFportIP
                dict1 = {'ID': query_electric.ID, 'ZGL': query_electric.ZGL, 'Unit': query_electric.Unit,
                         'AreaName': item.AreaName, 'CollectionDate': str(item.CollectionDate),
                         'IncremenValue': item.IncremenValue, 'TagClassValue': tag_area, 'AU': query_electric.AU,
                         'AI': query_electric.AI, 'BU': query_electric.BI, 'BI': query_electric.BI,
                         'CU': query_electric.CU, 'CI': query_electric.CI}
                data.append(dict1)
            if tag_point:
                price_sql = "select sum(t1.price)*12*1.2 total_price from (select TagClassValue,sum(cast(IncremenValue" \
                            " as float)) as price from [DB_MICS].[dbo].[IncrementElectricTable] where cast(IncremenValue as" \
                            " float) != 0.0 and TagClassValue in " + (str(tag_point).replace('[', '(')).replace(']',')') +\
                            " and CollectionDate between " + "'" + start_time + "'" + " and " + "'" + end_time + "'" +\
                            " group by TagClassValue) t1"
                total_price = db_session.execute(price_sql).fetchall()
                price = 0 if total_price[0]['total_price'] is None else str(round(total_price[0]['total_price'], 2))
                return json.dumps({'rows': data, 'total_column': result2[0]['total'], 'price': price}, cls=AlchemyEncoder,
                                  ensure_ascii=False)
            else:
                price_sql = "select sum(t1.price)*12*1.2 total_price from (select TagClassValue,sum(cast(IncremenValue" \
                            " as float)) as price from [DB_MICS].[dbo].[IncrementElectricTable] where cast(IncremenValue as" \
                            " float) != 0.0 and AreaName=" + "'" + area_name + "'" + " and CollectionDate between " +\
                            "'" + start_time + "'" + " and " + "'" + end_time + "'" + "group by TagClassValue) t1"
                total_price = db_session.execute(price_sql).fetchall()
                price = 0 if total_price[0]['total_price'] is None else str(round(total_price[0]['total_price'], 2))
                return json.dumps({'rows': result3, 'total_column': result2[0]['total'], 'price': price},
                                  cls=AlchemyEncoder, ensure_ascii=False)
        else:
            price_sql = "select sum(t1.price)*12*1.2 total_price from (select TagClassValue,sum(cast(IncremenValue" \
                        " as float)) as price from [DB_MICS].[dbo].[IncrementElectricTable] where cast(IncremenValue as" \
                        " float) != 0.0 and CollectionDate between " + "'" + start_time + "'" + " and " + "'" + end_time +\
                        "'" + "group by TagClassValue) t1"
            total_price = db_session.execute(price_sql).fetchall()
            price = 0 if total_price[0]['total_price'] is None else str(round(total_price[0]['total_price'], 2))
            rows = 'select top ' + str(pagesize) + ' CalculationID,TagClassValue,AreaName,IncremenValue,CollectionDate ' +\
                   'from [DB_MICS].[dbo].[IncrementElectricTable] where ID not in ' + '(select top ' + str(
                (current_page - 1) * pagesize) + ' ID from [DB_MICS].[dbo].[IncrementElectricTable] where cast(IncremenValue' \
                 ' as float) != 0.0 and CollectionDate between ' + "'" + start_time + "'" + " and " + "'" + end_time + "'" +\
                ' order by CollectionDate asc, ID asc)' + 'and cast(IncremenValue as float) != 0.0 and CollectionDate' \
                ' between ' + "'" + start_time + "'" + " and " + "'" + end_time + "'" + ' order by CollectionDate asc, ID asc'
            result3 = db_session.execute(rows).fetchall()
            total = 'select count(ID) as total from [DB_MICS].[dbo].[IncrementElectricTable] where cast(IncremenValue as' \
                    ' float) != 0.0 and CollectionDate between ' + "'" + start_time + "'" + " and" + "'" + end_time + "'"
            result2 = db_session.execute(total).fetchall()
            data = []
            for item in result3:
                if item.CalculationID and item.TagClassValue:
                    query_electric = db_session.query(ElectricEnergy).filter(ElectricEnergy.ID == item.CalculationID).first()
                    query_tagdetai = db_session.query(TagDetail).filter(
                        TagDetail.TagClassValue == item.TagClassValue).first()
                    tag_area = query_tagdetai.FEFportIP
                    dict1 = {'ID': query_electric.ID, 'ZGL': query_electric.ZGL, 'Unit': query_electric.Unit,
                             'AreaName': item.AreaName, 'CollectionDate': str(item.CollectionDate),
                             'IncremenValue': item.IncremenValue, 'TagClassValue': tag_area, 'AU': query_electric.AU,
                             'AI': query_electric.AI, 'BU': query_electric.BI, 'BI': query_electric.BI,
                             'CU': query_electric.CU, 'CI': query_electric.CI}
                    data.append(dict1)
            return json.dumps({'rows': data, 'total_column': result2[0]['total'], 'price': price}, cls=AlchemyEncoder,
                              ensure_ascii=False)
    except Exception as e:
        print(e)
        insertSyslog("error", "能耗查询报错Error：" + str(e), current_user.Name)
        return json.dumps([{"status": "Error：" + str(e)}], cls=AlchemyEncoder, ensure_ascii=False)


@energyElectric.route('/electricnergycost', methods=['POST', 'GET'])
def electricnergycost():
    '''
    成本中心-电度电费
    return:
    '''
    if request.method == 'GET':
        data = request.values
        try:
            dir = {}
            StartTime = data.get("StartTime")
            EndTime = data.get("EndTime")
            EnergyClass = "电"
            TimeClass = data.get("TimeClass")
            AreaName = data.get("AreaName")
            dir_list = []
            dir_list2 = []
            oc_list = []
            if AreaName == "" or AreaName == None:
                tags = db_session.query(TagDetail).filter(TagDetail.EnergyClass == EnergyClass).all()
            else:
                tags = db_session.query(TagDetail).filter(TagDetail.EnergyClass == EnergyClass,
                                                          TagDetail.AreaName == AreaName).all()
            for tag in tags:
                oc_list.append(tag.TagClassValue)
            jtime = 0.0
            ftime = 0.0
            ptime = 0.0
            gtime = 0.0
            jtimeprice = 0.0
            ftimeprice = 0.0
            ptimeprice = 0.0
            gtimeprice = 0.0
            if oc_list:
                if TimeClass == "日":
                    for i in range(int(StartTime[11:13]), int(EndTime[11:13]) + 1):
                        stae = StartTime[0:11] + addzero(i) + ":00:00"
                        ende = StartTime[0:11] + addzero(i) + ":59:59"
                        dir_list_i = {}
                        dir_list_i["时间"] = StartTime[0:11] + addzero(i)
                        # 尖峰平谷电量
                        elecs = timeelectric(oc_list, stae, ende, EnergyClass)
                        for ele in elecs:
                            if ele[0] == "尖时刻":
                                jtime = jtime + round(float(ele[1]), 2)
                                dir_list_i["尖时段"] = round(float(ele[1]), 2)
                            elif ele[0] == "峰时刻":
                                ftime = ftime + float(ele[1])
                                dir_list_i["峰时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "平时刻":
                                ptime = ptime + float(ele[1])
                                dir_list_i["平时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "谷时刻":
                                gtime = gtime + float(ele[1])
                                dir_list_i["谷时刻"] = round(float(ele[1]), 2)
                        # 尖峰平谷价格
                        dir_list_i_price = {}
                        dir_list_i_price["时间"] = StartTime[0:11] + addzero(i)
                        costs = timeelectricprice(oc_list, stae, ende, EnergyClass)
                        for ele in costs:
                            if ele[0] == "尖时刻":
                                jtimeprice = jtimeprice + round(float(ele[1]), 2)
                                dir_list_i_price["尖时段"] = round(float(ele[1]), 2)
                            elif ele[0] == "峰时刻":
                                ftimeprice = ftimeprice + float(ele[1])
                                dir_list_i_price["峰时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "平时刻":
                                ptimeprice = ptimeprice + float(ele[1])
                                dir_list_i_price["平时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "谷时刻":
                                gtimeprice = gtimeprice + float(ele[1])
                                dir_list_i_price["谷时刻"] = round(float(ele[1]), 2)
                        dir_list.append(dir_list_i)
                        dir_list2.append(dir_list_i_price)
                elif TimeClass == "月":
                    for i in range(int(StartTime[8:10]), int(EndTime[8:10]) + 1):
                        staeM = StartTime[0:8]+addzero(i) + " 00:00:00"
                        endeM = StartTime[0:8]+addzero(i) + " 23:59:59"
                        dir_list_i = {}
                        dir_list_i["时间"] = StartTime[0:8] + addzero(i)
                        # 尖峰平谷电量
                        elecs = timeelectric(oc_list, staeM, endeM, EnergyClass)
                        for ele in elecs:
                            if ele[0] == "尖时刻":
                                jtime = jtime + round(float(ele[1]), 2)
                                dir_list_i["尖时段"] = round(float(ele[1]), 2)
                            elif ele[0] == "峰时刻":
                                ftime = ftime + float(ele[1])
                                dir_list_i["峰时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "平时刻":
                                ptime = ptime + float(ele[1])
                                dir_list_i["平时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "谷时刻":
                                gtime = gtime + float(ele[1])
                                dir_list_i["谷时刻"] = round(float(ele[1]), 2)
                        # 尖峰平谷价格
                        dir_list_i_price = {}
                        dir_list_i_price["时间"] = StartTime[0:8] + addzero(i)
                        costs = timeelectricprice(oc_list, staeM, endeM, EnergyClass)
                        for ele in costs:
                            if ele[0] == "尖时刻":
                                jtimeprice = jtimeprice + round(float(ele[1]), 2)
                                dir_list_i_price["尖时段"] = round(float(ele[1]), 2)
                            elif ele[0] == "峰时刻":
                                ftimeprice = ftimeprice + float(ele[1])
                                dir_list_i_price["峰时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "平时刻":
                                ptimeprice = ptimeprice + float(ele[1])
                                dir_list_i_price["平时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "谷时刻":
                                gtimeprice = gtimeprice + float(ele[1])
                                dir_list_i_price["谷时刻"] = round(float(ele[1]), 2)
                        dir_list.append(dir_list_i)
                        dir_list2.append(dir_list_i_price)
                elif TimeClass == "年":
                    for i in range(int(StartTime[5:7]), int(EndTime[5:7]) + 1):
                        staeY = StartTime[0:5] + addzero(i) + "-01 00:00:00"
                        eyear = getMonthFirstDayAndLastDay(StartTime[0:4], i)
                        endeY = datetime.datetime.strftime(eyear[1], "%Y-%m-%d") + " 23:59:59"
                        dir_list_i = {}
                        dir_list_i["时间"] = StartTime[0:5] + addzero(i)
                        # 尖峰平谷电量
                        elecs = timeelectric(oc_list, staeY, endeY, EnergyClass)
                        for ele in elecs:
                            if ele[0] == "尖时刻":
                                jtime = jtime + round(float(ele[1]), 2)
                                dir_list_i["尖时段"] = round(float(ele[1]), 2)
                            elif ele[0] == "峰时刻":
                                ftime = ftime + float(ele[1])
                                dir_list_i["峰时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "平时刻":
                                ptime = ptime + float(ele[1])
                                dir_list_i["平时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "谷时刻":
                                gtime = gtime + float(ele[1])
                                dir_list_i["谷时刻"] = round(float(ele[1]), 2)
                        # 尖峰平谷价格
                        dir_list_i_price = {}
                        dir_list_i_price["时间"] = StartTime[0:5] +addzero(i)
                        costs = timeelectricprice(oc_list, staeY, endeY, EnergyClass)
                        for ele in costs:
                            if ele[0] == "尖时刻":
                                jtimeprice = jtimeprice + round(float(ele[1]), 2)
                                dir_list_i_price["尖时段"] = round(float(ele[1]), 2)
                            elif ele[0] == "峰时刻":
                                ftimeprice = ftimeprice + float(ele[1])
                                dir_list_i_price["峰时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "平时刻":
                                ptimeprice = ptimeprice + float(ele[1])
                                dir_list_i_price["平时刻"] = round(float(ele[1]), 2)
                            elif ele[0] == "谷时刻":
                                gtimeprice = gtimeprice + float(ele[1])
                                dir_list_i_price["谷时刻"] = round(float(ele[1]), 2)
                        dir_list.append(dir_list_i)
                        dir_list2.append(dir_list_i_price)
            unit = db_session.query(Unit.UnitValue).filter(Unit.UnitName == EnergyClass).first()[0]
            priceunits = db_session.query(ElectricPrice).filter().all()
            for priceunit in priceunits:
                if priceunit.PriceName == "尖时刻":
                    juint = float(priceunit.PriceValue)
                elif priceunit.PriceName == "峰时刻":
                    fuint = float(priceunit.PriceValue)
                elif priceunit.PriceName == "平时刻":
                    puint = float(priceunit.PriceValue)
                elif priceunit.PriceName == "谷时刻":
                    guint = float(priceunit.PriceValue)
            totalprice = jtimeprice + ftimeprice + ptimeprice + gtimeprice
            periodTimeTypeItem = []
            if totalprice != 0.0:
                jratio = round((jtimeprice / totalprice) * 100, 2)
                fratio = round((ftimeprice / totalprice) * 100, 2)
                pratio = round((ptimeprice / totalprice) * 100, 2)
                gratio = round((gtimeprice / totalprice) * 100, 2)
            else:
                jratio = 0
                fratio = 0
                pratio = 0
                gratio = 0
            dir_jtime = {}
            dir_jtime["title"] = "尖时刻"
            dir_jtime["expendEnergy"] = round(jtime, 2)
            dir_jtime["expendPrice"] = round(jtimeprice, 2)
            dir_jtime["unit"] = unit
            dir_jtime["Ratio"] = jratio
            dir_jtime["unitPrice"] = juint
            dir_jtime["color"] = "#FB3A06"
            periodTimeTypeItem.append(dir_jtime)
            dir_ftime = {}
            dir_ftime["title"] = "峰时刻"
            dir_ftime["expendEnergy"] = round(ftime, 2)
            dir_ftime["expendPrice"] = round(ftimeprice, 2)
            dir_ftime["unit"] = unit
            dir_ftime["Ratio"] = fratio
            dir_ftime["unitPrice"] = fuint
            dir_ftime["color"] = "#FB8A06"
            periodTimeTypeItem.append(dir_ftime)
            dir_ptime = {}
            dir_ptime["title"] = "平时刻"
            dir_ptime["expendEnergy"] = round(ptime, 2)
            dir_ptime["expendPrice"] = round(ptimeprice, 2)
            dir_ptime["unit"] = unit
            dir_ptime["Ratio"] = pratio
            dir_ptime["unitPrice"] = puint
            dir_ptime["color"] = "#F8E71C"
            periodTimeTypeItem.append(dir_ptime)
            dir_gtime = {}
            dir_gtime["title"] = "谷时刻"
            dir_gtime["expendEnergy"] = round(gtime, 2)
            dir_gtime["expendPrice"] = round(gtimeprice, 2)
            dir_gtime["unit"] = unit
            dir_gtime["Ratio"] = gratio
            dir_gtime["unitPrice"] = guint
            dir_gtime["color"] = "#15CC48"
            periodTimeTypeItem.append(dir_gtime)
            dir["periodTimeTypeItem"] = periodTimeTypeItem
            dir["rows1"] = dir_list
            dir["rows2"] = dir_list2
            dir["totalPrice"] = round(jtimeprice + ftimeprice + ptimeprice + gtimeprice, 2)
            return json.dumps(dir, cls=AlchemyEncoder, ensure_ascii=False)
        except Exception as e:
            print(e)
            logger.error(e)
            insertSyslog("error", "成本中心-电度电费查询报错Error：" + str(e), current_user.Name)


def timeelectricprice(oc_list, StartTime, EndTime, energy):
    re_list = []
    jtotal = 0.0
    ftotal = 0.0
    ptotal = 0.0
    gtotal = 0.0
    for tag in oc_list:
        # ratios = db_session.query(ElectricSiteURL).filter(ElectricSiteURL.TagClassValue == tag).first()
        # value = ratios.Value
        # sql = "select t2.PriceName,SUM(Cast(t1.IncremenValue as float))*" + value + "* Cast(t2.PriceValue as float) FROM [DB_MICS].[dbo].[IncrementElectricTable] t1 with (INDEX =IX_IncrementElectricTable) INNER JOIN [DB_MICS].[dbo].[ElectricPrice] t2 ON t1.PriceID = t2.ID where  t1.TagClassValue='" + tag + "' and t1.CollectionDate BETWEEN " + "'" + StartTime + "'" + " AND " + "'" + EndTime + "' group by t1.PriceID, t2.PriceValue, t2.PriceName"
        sql = "select t2.PriceName,SUM(Cast(t1.IncremenValue as float))*Cast(t2.PriceValue as float) FROM [DB_MICS].[dbo].[IncrementElectricTable] t1 with (INDEX =IX_IncrementElectricTable) INNER JOIN [DB_MICS].[dbo].[ElectricPrice] t2 ON t1.PriceID = t2.ID where  t1.TagClassValue='" + tag + "' and t1.CollectionDate BETWEEN " + "'" + StartTime + "'" + " AND " + "'" + EndTime + "' group by t1.PriceID, t2.PriceValue, t2.PriceName"
        res = db_session.execute(sql).fetchall()
        for re in res:
            if re[0] == "尖时刻":
                j = re[1] if re[1] is not None else 0.0
                jtotal = jtotal + j
            elif re[0] == "峰时刻":
                f = re[1] if re[1] is not None else 0.0
                ftotal = ftotal + f
            elif re[0] == "平时刻":
                p = re[1] if re[1] is not None else 0.0
                ptotal = ptotal + p
            elif re[0] == "谷时刻":
                g = re[1] if re[1] is not None else 0.0
                gtotal = gtotal + g
        # if len(re) > 0:
        #     price_name = re[0][0]
        #     zgl = re[0][1] if re[0][1] is not None else 0.0
        #     total += zgl
        db_session.close()
    re_list.append(("尖时刻",jtotal))
    re_list.append(("峰时刻",ftotal))
    re_list.append(("平时刻",ptotal))
    re_list.append(("谷时刻",gtotal))
    return re_list
                    #[(price_name, total)]
    # sql = "select t2.PriceName,SUM(Cast(t1.IncremenValue as float)) * Cast(t2.PriceValue as float) FROM [DB_MICS].[dbo].[IncrementElectricTable] t1 with (INDEX =IX_IncrementElectricTable) INNER JOIN [DB_MICS].[dbo].[ElectricPrice] t2 ON t1.PriceID = t2.ID where  t1.TagClassValue in (" + str(
    #     oc_list)[
    #                                                                                                                                                                                                                                                                                             1:-1] + ") and t1.CollectionDate BETWEEN " + "'" + StartTime + "'" + " AND " + "'" + EndTime + "' group by t1.PriceID, t2.PriceValue, t2.PriceName"
    # re = db_session.execute(sql).fetchall()
    # db_session.close()
    # return re


def timeelectric(oc_list, StartTime, EndTime, energy):
    total = 0.0
    price_name = ''
    for tag in oc_list:
        # ratios = db_session.query(ElectricSiteURL).filter(ElectricSiteURL.TagClassValue == tag).first()
        # value = ratios.Value
        sql = "select t2.PriceName,SUM(Cast(t1.IncremenValue as float)) FROM [DB_MICS].[dbo].[IncrementElectricTable] t1 with (INDEX =IX_IncrementElectricTable) INNER JOIN [DB_MICS].[dbo].[ElectricPrice] t2 ON t1.PriceID = t2.ID where  t1.TagClassValue='" + tag +"' and t1.CollectionDate BETWEEN " + "'" + StartTime + "'" + " AND " + "'" + EndTime + "' group by t1.PriceID, t2.PriceValue, t2.PriceName"
        re = db_session.execute(sql).fetchall()
        if len(re) > 0:
            price_name = re[0][0]
            zgl = re[0][1] if re[0][1] is not None else 0.0
            total += zgl
        else:
            pass
        # db_session.close()
        # print('单个tag点总功率:', tag, total)
    # print('hello1')
    # print('hello2:', price_name)
    # print('hello3:', total)
    return [(price_name, total)]
    # sql = "select t2.PriceName,SUM(Cast(t1.IncremenValue as float)) FROM [DB_MICS].[dbo].[IncrementElectricTable] t1 with (INDEX =IX_IncrementElectricTable) INNER JOIN [DB_MICS].[dbo].[ElectricPrice] t2 ON t1.PriceID = t2.ID where  t1.TagClassValue in (" + str(
    #     oc_list)[
    #                                                                                                                                                                                                                                                              1:-1] + ") and t1.CollectionDate BETWEEN " + "'" + StartTime + "'" + " AND " + "'" + EndTime + "' group by t1.PriceID, t2.PriceValue, t2.PriceName"
    #
    # re = db_session.execute(sql).fetchall()
    # db_session.close()
    # return re



@energyElectric.route('/runefficiency', methods=['POST', 'GET'])
def runefficiency():
    '''
    运行效率
    return:
    '''
    if request.method == 'GET':
        data = request.values
        try:
            dir = {}
            StartTime = data.get("StartTime")
            EndTime = data.get("EndTime")
            TimeClass = data.get("TimeClass")
            CurrentTime = data.get("CurrentTime")
            AreaName = data.get("AreaName")
            EnergyClass = "电"
            oc_list = []
            if AreaName == "" or AreaName == None:
                tags = db_session.query(TagDetail).filter(TagDetail.EnergyClass == EnergyClass).all()
                rpms = \
                    db_session.query(RatedPowerMaintain).filter().all()
            else:
                tags = db_session.query(TagDetail).filter(TagDetail.EnergyClass == EnergyClass,
                                                          TagDetail.AreaName == AreaName).all()
                rpms = \
                    db_session.query(RatedPowerMaintain).filter(RatedPowerMaintain.AreaName == AreaName).all()
            for tag in tags:
                oc_list.append(tag.TagClassValue)
            dict_rpms = {}
            for rpm in rpms:
                dict_rpms[rpm.AreaName] = rpm.RatedPowerValue
            if oc_list:
                runes = loadRateTotal(oc_list, CurrentTime[0:10]+" 00:00:00", CurrentTime[0:10]+" 23:59:59", EnergyClass)
                runes = round(0 if runes[0]['Rate'] is None else float(runes[0]['Rate']), 2)
                dir["activePower"] = runes
            else:
                dir["activePower"] = 0
                runes = 0
            if AreaName == "" or AreaName == None:
                dir["ratedPower"] = dict_rpms["全厂"]
                if runes != 0:
                    rune = round((runes/24)/float(dict_rpms["全厂"]), 2)
                else:
                    rune = 0
            else:
                dir["ratedPower"] = dict_rpms[AreaName]
                if runes != 0:
                    rune = round((runes / 24) / float(dict_rpms[AreaName]), 2)
                else:
                    rune = 0
            dir["loadRate"] = round((rune)*100, 2)
            unit = db_session.query(Unit.UnitValue).filter(Unit.UnitName == EnergyClass).first()[0]
            dir["unit"] = unit
            dir_list = []
            if oc_list:
                if TimeClass == "日":
                    sql = "SELECT Sum(Cast(t.IncremenValue as float))*(select Cast([Proportion] as float) from [DB_MICS].[dbo].[ElectricProportion] where [ProportionType] = '" + EnergyClass + "'),t.CollectionHour FROM [DB_MICS].[dbo].[IncrementElectricTable] t with (INDEX =IX_IncrementElectricTable)  WHERE t.TagClassValue in (" + str(
                        oc_list)[
                                                                                                                                                                                                                                                                                                                                       1:-1] + ") AND t.CollectionDate BETWEEN " + "'" + StartTime[0:10] + " 00:00:00" + "'" + " AND " + "'" + EndTime[0:10] + " 23:59:59" + "' group by t.CollectionHour"
                    rehours = db_session.execute(sql).fetchall()
                    db_session.close()
                    dict_rehours = {letter: score for score, letters in rehours for letter in letters.split(",")}
                    for myhour in constant.myHours:
                        myhourcurr = StartTime[0:10] + " " + myhour
                        runehou = 0
                        if AreaName == None or AreaName == "":
                            if myhourcurr in dict_rehours.keys():
                                runehou = float(dict_rehours[myhourcurr]) / float(dict_rpms["全厂"])
                        else:
                            if myhourcurr in dict_rehours.keys():
                                runehou = float(dict_rehours[myhourcurr]) / float(dict_rpms[AreaName])
                        dir_list_i = {}
                        sttimeArray = time.strptime(myhourcurr, '%Y-%m-%d %H')
                        sttime = int(time.mktime(sttimeArray))
                        nowtime = int(round(time.time()))
                        if sttime > nowtime:
                            dir_list_i["时间"] = myhourcurr
                            dir_list_i["负荷率"] = ""
                        else:
                            dir_list_i["时间"] = myhourcurr
                            dir_list_i["负荷率"] = round(100 * runehou, 2)
                        dir_list.append(dir_list_i)
                elif TimeClass == "月":
                    sql = "SELECT Sum(Cast(t.IncremenValue as float))*(select Cast([Proportion] as float) from [DB_MICS].[dbo].[ElectricProportion] where [ProportionType] = '" + EnergyClass + "'),t.CollectionDay FROM [DB_MICS].[dbo].[IncrementElectricTable] t with (INDEX =IX_IncrementElectricTable)  WHERE t.TagClassValue in (" + str(
                        oc_list)[
                                                                                                                                                                                                                                                                                                                                       1:-1] + ") AND t.CollectionDate BETWEEN " + "'" + StartTime[0:10] + " 00:00:00" + "'" + " AND " + "'" + EndTime[0:10] + " 23:59:59" + "' group by t.CollectionDay"
                    redays = db_session.execute(sql).fetchall()
                    db_session.close()
                    dict_redays = {letter: score for score, letters in redays for letter in letters.split(",")}
                    for myday in constant.mydays:
                        mydaycurr = StartTime[0:8] + myday
                        runeday = 0
                        if AreaName == None or AreaName == "":
                            if mydaycurr in dict_redays.keys():
                                runeday = (float(dict_redays[mydaycurr])/24) / float(dict_rpms["全厂"])
                        else:
                            if mydaycurr in dict_redays.keys():
                                runeday = (float(dict_redays[mydaycurr]) / 24) / float(dict_rpms[AreaName])
                        returnmonthfirstend = getMonthFirstDayAndLastDay(StartTime[0:4], StartTime[5:7])
                        if int(myday) <= int(str(returnmonthfirstend[1])[8:10]):
                            dir_list_i = {}
                            sttimeArray = time.strptime(mydaycurr, '%Y-%m-%d')
                            sttime = int(time.mktime(sttimeArray))
                            nowtime = int(round(time.time()))
                            if sttime > nowtime:
                                dir_list_i["时间"] = mydaycurr
                                dir_list_i["负荷率"] = ""
                            else:
                                dir_list_i["时间"] = mydaycurr
                                dir_list_i["负荷率"] = round(100 * runeday, 2)
                            dir_list.append(dir_list_i)
                elif TimeClass == "年":
                    sql = "SELECT Sum(Cast(t.IncremenValue as float))*(select Cast([Proportion] as float) from [DB_MICS].[dbo].[ElectricProportion] where [ProportionType] = '" + EnergyClass + "'),t.CollectionMonth FROM [DB_MICS].[dbo].[IncrementElectricTable] t with (INDEX =IX_IncrementElectricTable)  WHERE t.TagClassValue in (" + str(
                        oc_list)[
                                                                                                                                                                                                                                                                                                                                       1:-1] + ") AND t.CollectionDate BETWEEN " + "'" + StartTime[0:10] + " 00:00:00" + "'" + " AND " + "'" + EndTime[0:10] + " 23:59:59" + "' group by t.CollectionMonth"
                    remonths = db_session.execute(sql).fetchall()
                    db_session.close()
                    dict_remonths = {letter: score for score, letters in remonths for letter in letters.split(",")}
                    for myonth in constant.mymonths:
                        myonthcurr = StartTime[0:5] + myonth
                        runemonth = 0
                        if AreaName == None or AreaName == "":
                            if myonthcurr in dict_remonths.keys():
                                runemonth = (float(dict_remonths[myonthcurr]) / (30*24)) / float(dict_rpms["全厂"])
                        else:
                            if myonthcurr in dict_remonths.keys():
                                runemonth = (float(dict_remonths[myonthcurr]) / (30*24)) / float(dict_rpms[AreaName])
                        dir_list_i = {}
                        sttimeArray = time.strptime(myonthcurr, '%Y-%m')
                        sttime = int(time.mktime(sttimeArray))
                        nowtime = int(round(time.time()))
                        if sttime > nowtime:
                            dir_list_i["时间"] = myonthcurr
                            dir_list_i["负荷率"] = ""
                        else:
                            dir_list_i["时间"] = myonthcurr
                            dir_list_i["负荷率"] = round(100 * runemonth, 2)
                        dir_list.append(dir_list_i)
            dir["row"] = dir_list
            return json.dumps(dir)
        except Exception as e:
            print(e)
            logger.error(e)
            insertSyslog("error", "运行效率查询报错Error：" + str(e), current_user.Name)

def loadRateTotal(oc_list, StartTime, EndTime, energy):
    sql = "SELECT Sum(Cast(t.IncremenValue as float))*(select Cast([Proportion] as float) from [DB_MICS].[dbo].[ElectricProportion] where [ProportionType] = '"+energy+"') as Rate FROM [DB_MICS].[dbo].[IncrementElectricTable] t with (INDEX =IX_IncrementElectricTable)  WHERE t.TagClassValue in (" + str(oc_list)[1:-1] + ") AND t.CollectionDate BETWEEN " + "'" + StartTime + "'" + " AND " + "'" + EndTime + "'"
    re = db_session.execute(sql).fetchall()
    db_session.close()
    return re

