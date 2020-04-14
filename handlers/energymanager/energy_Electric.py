import redis
from flask import Blueprint, render_template, request, make_response, send_file, jsonify
import json
import datetime
from sqlalchemy import desc
from dbset.database.db_operate import db_session, pool
from dbset.main.BSFramwork import AlchemyEncoder
from flask_login import login_required, logout_user, login_user, current_user, LoginManager
import calendar

from handlers.energymanager.energy_manager import energyStatistics
from models.SystemManagement.core import RedisKey, ElectricEnergy, WaterEnergy, SteamEnergy, LimitTable, Equipment, \
    AreaTable, Unit, TagClassType, TagDetail, BatchMaintain
from models.SystemManagement.system import EarlyWarning, EarlyWarningLimitMaintain, WaterSteamBatchMaintain, \
    AreaTimeEnergyColour, ElectricProportion, IncrementElectricTable
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
                oc_list.append(oc.TagClassValue)
            if len(oc_list) > 0:
                elecount = energyStatistics(oc_list, StartTime, EndTime, energy)
            else:
                elecount = 0.0
            dir["value"] = elecount
            dir["type"] = "电"
            unit = db_session.query(Unit.UnitValue).filter(Unit.UnitName == energy).first()[0]
            dir["unit"] = unit
            #成本

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
    start_time = request.values.get('start_time')
    end_time = request.values.get('end_time')
    # 当前页数
    current_page = int(request.values.get('offset'))
    # 每页显示条数
    pagesize = int(request.values.get('limit'))
    area_name = request.values.get('area_name')
    if area_name:
        rows = db_session.query(IncrementElectricTable).filter(IncrementElectricTable.AreaName == area_name).filter(IncrementElectricTable.CollectionDate.between(start_time, end_time)).all()[(current_page - 1) * pagesize + 1:current_page * pagesize + 1]
        total = len(db_session.query(IncrementElectricTable).filter(IncrementElectricTable.AreaName == area_name).filter(IncrementElectricTable.CollectionDate.between(start_time, end_time)).all())
        tag_list = db_session.query(TagDetail).filter(TagDetail.AreaName == area_name, TagDetail.EnergyClass == '电').all()
        tag_point = [index.TagClassValue for index in tag_list]
        data = []
        for item in rows:
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
            sql = "select sum(cast(t1.IncremenValue as decimal(9,2)))*12*1.2 as count from [DB_MICS].[dbo].[IncrementElectricTable] t1 where t1.TagClassValue in " + (str(tag_point).replace('[', '(')).replace(']', ')') + " and t1.CollectionDate between " + "'" + start_time + "'" + " and" + "'" + end_time + "'" + " group by t1.IncremenType"
            result = db_session.execute(sql).fetchall()
            price = 0 if len(result) == 0 else str(round(result[0]['count'], 2))
            return json.dumps({'rows': data, 'total_column': total, 'price': price}, cls=AlchemyEncoder, ensure_ascii=False)
        else:
            sql = "select sum(cast(t1.IncremenValue as decimal(9,2)))*12*1.2 as count from [DB_MICS].[dbo].[IncrementElectricTable] t1 where " + "t1.CollectionDate between " + "'" + start_time + "'" + " and" + "'" + end_time + "'" + " group by t1.IncremenType"
            result = db_session.execute(sql).fetchall()
            price = 0 if len(result) == 0 else str(round(result[0]['count'], 2))
            return json.dumps({'rows': rows, 'total_column': total, 'price': price}, cls=AlchemyEncoder, ensure_ascii=False)
    else:
        tag_list = db_session.query(TagDetail).filter(TagDetail.EnergyClass == '电').all()
        tag_point = [index.TagClassValue for index in tag_list]
        sql = "select t1.AreaName, sum(cast(t1.IncremenValue as decimal(9,2)))*12*1.2 as count from [DB_MICS].[dbo].[IncrementElectricTable] t1 where t1.TagClassValue in " + (str(tag_point).replace('[', '(')).replace(']', ')') + "and t1.CollectionDate between " + "'" + start_time + "'" + " and" + "'" + end_time + "'" + " group by t1.AreaName"
        rows = db_session.query(IncrementElectricTable).filter(IncrementElectricTable.CollectionDate.between(start_time, end_time)).all()[(current_page - 1) * pagesize + 1:current_page * pagesize + 1]
        total = len(db_session.query(IncrementElectricTable).filter(IncrementElectricTable.CollectionDate.between(start_time, end_time)).all())
        data = []
        for item in rows:
            query_electric = db_session.query(ElectricEnergy).filter(ElectricEnergy.ID == item.CalculationID).first()
            query_tagdetai = db_session.query(TagDetail).filter(TagDetail.TagClassValue == item.TagClassValue).first()
            tag_area = query_tagdetai.FEFportIP
            dict1 = {'ID': query_electric.ID, 'ZGL': query_electric.ZGL, 'Unit': query_electric.Unit,
                     'AreaName': item.AreaName, 'CollectionDate': str(item.CollectionDate),
                     'IncremenValue': item.IncremenValue, 'TagClassValue': tag_area, 'AU': query_electric.AU,
                     'AI': query_electric.AI, 'BU': query_electric.BI, 'BI': query_electric.BI,
                     'CU': query_electric.CU, 'CI': query_electric.CI}
            data.append(dict1)
        result = db_session.execute(sql).fetchall()
        price = 0 if len(result) == 0 else str(round(result[0]['count'], 2))
        return json.dumps({'rows': data, 'total_column': total, 'price': price}, cls=AlchemyEncoder, ensure_ascii=False)
