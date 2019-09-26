import redis
from flask import Blueprint, render_template, request, make_response
import json
import datetime
from sqlalchemy import desc
from dbset.database.db_operate import db_session,pool
from dbset.main.BSFramwork import AlchemyEncoder
from flask_login import login_required, logout_user, login_user,current_user,LoginManager
import calendar
from models.SystemManagement.core import RedisKey, ElectricEnergy, WaterEnergy, SteamEnergy, LimitTable
from tools.common import insert,delete,update
from dbset.database import constant
from dbset.log.BK2TLogger import logger,insertSyslog
import datetime
import arrow

energy = Blueprint('energy', __name__, template_folder='templates')
@energy.route('/energyRedisData')
def energyRedisData():
    return render_template('./energyRedisData.html')

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
@energy.route('/energyTrend', methods=['POST', 'GET'])
def energyTrend():
    '''
    能耗趋势
    :return:
    '''
    if request.method == 'GET':
        data = request.values
        try:
            currenttime = data.get("currenttime")
            classparam = data.get("classparam")
            currentyear = datetime.datetime.now().year
            currentmonth = datetime.datetime.now().month
            currentday = datetime.datetime.now().day
            currenthour = datetime.datetime.now().hour
            dir = {}
            dix = []
            diy = []
            diyr = {}
            diyz = []
            if currenttime == "年":
                for j in range(1,currentmonth+1):
                    mon = str(currentyear) + "-" + addzero(j)
                    dix.append(str(j))
                    if classparam == "电":
                        EnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(ElectricEnergy.CollectionMonth == mon).all()
                    elif classparam == "水":
                        EnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                            WaterEnergy.CollectionMonth == mon).all()
                    elif classparam == "汽":
                        EnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                            SteamEnergy.CollectionMonth == mon).all()
                    diyz.append(accumulation(EnergyValues))
            elif currenttime == "月":#2019-9-22
                for j in range(1, currentday+1):
                    day = str(currentyear) + "-" + addzero(currentmonth) + "-" + addzero(j)
                    dix.append(str(j))
                    if classparam == "电":
                        EnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(
                            ElectricEnergy.CollectionDay == day).all()
                    elif classparam == "水":
                        EnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                            WaterEnergy.CollectionDay == day).all()
                    elif classparam == "汽":
                        EnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                            SteamEnergy.CollectionDay == day).all()
                    diyz.append(accumulation(EnergyValues))
            elif currenttime == "日":
                for j in range(0, currenthour):
                    hour = str(currentyear) + "-" + addzero(currentmonth) + "-" + addzero(currentday) + " " + addzero(j)
                    dix.append(str(j))
                    if classparam == "电":
                        EnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(
                            ElectricEnergy.CollectionDate.like("%"+hour+"%")).all()
                    elif classparam == "水":
                        EnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                            WaterEnergy.CollectionDate.like("%"+hour+"%")).all()
                    elif classparam == "汽":
                        EnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                            SteamEnergy.CollectionDate.like("%"+hour+"%")).all()
                    diyz.append(accumulation(EnergyValues))
            diyr["name"] = classparam
            diyr["data"] = diyz
            dir["X"] = dix
            diy.append(diyr)
            dir["Y"] = diy
            print(dir)
            return json.dumps(dir, cls=AlchemyEncoder, ensure_ascii=False)
        except Exception as e:
            print(e)
            logger.error(e)
            insertSyslog("error", "能耗趋势查询报错Error：" + str(e), current_user.Name)

def limitappend(currEnergyValues,lastEnergyValues,name,tim):
    '''
    :param EnergyValues: 能耗数组
    :param name: 水电汽
    :param tim: 年月日
    :return:
    '''
    curr = accumulation(currEnergyValues)
    last = accumulation(lastEnergyValues)
    trend = ""
    if curr>last:
        trend = "上升"
    elif curr==last:
        trend = "相等"
    else:
        trend = "下降"
    Ywatlimit = db_session.query(LimitTable.LimitValue).filter(LimitTable.LimitName.like("%"+name+"%")).first()[0]
    limit = float(Ywatlimit)
    if tim == "月":
        limit = limit/12
    elif tim == "日":
        limit = limit/365
    ews = {}
    ews["name"] = name
    ews["upperLimit"] = str(limit)
    ews["percent"] = str(curr/limit) + "%"
    ews["value"] = str(curr)
    ews["trend"] = trend
    return ews
@energy.route('/energySumPercent', methods=['POST', 'GET'])
def energySumPercent():
    '''
    分项能耗量
    :return:
    '''
    if request.method == 'GET':
        data = request.values
        try:
            currenttime = data.get("currenttime")
            dir = {}
            a = arrow.now()
            currentyear = str(a.shift(years=0))[0:4]
            currentmonth = str(a.shift(years=0))[0:7]
            currentday = str(a.shift(days=0))[0:10]
            lastyear = str(a.shift(years=-1))[0:4]
            lastmonth = str(a.shift(months=-1))[0:7]
            lastday = str(a.shift(days=-1))[0:10]#a.shift(weeks=1)
            dic = []
            if currenttime == "年":
                curreleEnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(
                    ElectricEnergy.CollectionYear == currentyear).all()
                lasteleEnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(
                    ElectricEnergy.CollectionYear == lastyear).all()
                dic.append(limitappend(curreleEnergyValues,lasteleEnergyValues,"电",currenttime))
                currwatEnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                    WaterEnergy.CollectionYear == currentyear).all()
                lastwatEnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                    WaterEnergy.CollectionYear == lastyear).all()
                dic.append(limitappend(currwatEnergyValues, lastwatEnergyValues, "水", currenttime))
                currsteEnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                    SteamEnergy.CollectionYear == currentyear).all()
                laststeEnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                    SteamEnergy.CollectionYear == lastyear).all()
                dic.append(limitappend(currsteEnergyValues, laststeEnergyValues, "汽", currenttime))
            elif currenttime == "月":
                curreleEnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(
                    ElectricEnergy.CollectionMonth == currentmonth).all()
                lasteleEnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(
                    ElectricEnergy.CollectionMonth == lastmonth).all()
                dic.append(limitappend(curreleEnergyValues, lasteleEnergyValues, "电", currenttime))
                currwatEnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                    WaterEnergy.CollectionMonth == currentmonth).all()
                lastwatEnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                    WaterEnergy.CollectionMonth == lastmonth).all()
                dic.append(limitappend(currwatEnergyValues, lastwatEnergyValues, "水", currenttime))
                currsteEnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                    SteamEnergy.CollectionMonth == currentmonth).all()
                laststeEnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                    SteamEnergy.CollectionMonth == lastmonth).all()
                dic.append(limitappend(currsteEnergyValues, laststeEnergyValues, "汽", currenttime))
            elif currenttime == "日":
                curreleEnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(
                    ElectricEnergy.CollectionDay == currentday).all()
                lasteleEnergyValues = db_session.query(ElectricEnergy.ElectricEnergyValue).filter(
                    ElectricEnergy.CollectionDay == lastday).all()
                dic.append(limitappend(curreleEnergyValues, lasteleEnergyValues, "电", currenttime))
                currwatEnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                    WaterEnergy.CollectionDay == currentday).all()
                lastwatEnergyValues = db_session.query(WaterEnergy.WaterMeterValue).filter(
                    WaterEnergy.CollectionDay == lastday).all()
                dic.append(limitappend(currwatEnergyValues, lastwatEnergyValues, "水", currenttime))
                currsteEnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                    SteamEnergy.CollectionDay == currentday).all()
                laststeEnergyValues = db_session.query(SteamEnergy.SteamValue).filter(
                    SteamEnergy.CollectionDay == lastday).all()
                dic.append(limitappend(currsteEnergyValues, laststeEnergyValues, "汽", currenttime))
            return json.dumps(dic, cls=AlchemyEncoder, ensure_ascii=False)
        except Exception as e:
            print(e)
            logger.error(e)
            insertSyslog("error", "分项能耗量查询报错Error：" + str(e), current_user.Name)