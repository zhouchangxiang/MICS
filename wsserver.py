import redis
import json
from dbset.database import constant
import time
from tools.MESLogger import MESLogger
logger = MESLogger('../logs', 'log')
import socket
import struct
import hashlib
import base64
import threading
import random
import datetime
from dbset.database.db_operate import db_session
from models.SystemManagement.system import ElectricSiteURL
from models.SystemManagement.core import TagDetail, AreaTable
from dbset.log.BK2TLogger import logger,insertSyslog


def get_headers(data):
    headers = {}
    data = str(data, encoding="utf-8")

    header, body = data.split("\r\n\r\n", 1)

    header_list = header.split("\r\n")

    for i in header_list:
        i_list = i.split(":", 1)
        if len(i_list) >= 2:
            headers[i_list[0]] = "".join(i_list[1::]).strip()
        else:
            i_list = i.split(" ", 1)
            if i_list and len(i_list) == 2:
                headers["method"] = i_list[0]
                headers["protocol"] = i_list[1]
    return headers


def parse_payload(payload):
    payload_len = payload[1] & 127
    if payload_len == 126:
        extend_payload_len = payload[2:4]
        mask = payload[4:8]
        decoded = payload[8:]

    elif payload_len == 127:
        extend_payload_len = payload[2:10]
        mask = payload[10:14]
        decoded = payload[14:]
    else:
        extend_payload_len = None
        mask = payload[2:6]
        decoded = payload[6:]

    # 这里我们使用字节将数据全部收集，再去字符串编码，这样不会导致中文乱码
    bytes_list = bytearray()

    for i in range(len(decoded)):
        # 解码方式
        chunk = decoded[i] ^ mask[i % 4]
        bytes_list.append(chunk)
    body = str(bytes_list, encoding='utf-8')
    return body


def send_msg(conn, msg_bytes):
    # 接收的第一字节，一般都是x81不变
    first_byte = b"\x81"
    length = len(msg_bytes)
    if length < 126:
        first_byte += struct.pack("B", length)
    elif length <= 0xFFFF:
        first_byte += struct.pack("!BH", 126, length)
    else:
        first_byte += struct.pack("!BQ", 127, length)

    msg = first_byte + msg_bytes
    conn.sendall(msg)
    return True

sock_pool = []


def handler_accept(sock):

    while True:
        conn, addr = sock.accept()

        data = conn.recv(8096)
        headers = get_headers(data)
        # 对请求头中的sec-websocket-key进行加密
        response_tpl = "HTTP/1.1 101 Switching Protocols\r\n" \
                       "Upgrade:websocket\r\n" \
                       "Connection: Upgrade\r\n" \
                       "Sec-WebSocket-Accept: %s\r\n" \
                       "WebSocket-Location: ws://%s\r\n\r\n"

        # 第一次连接发回报文
        magic_string = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        if headers.get('Sec-WebSocket-Key'):
            value = headers['Sec-WebSocket-Key'] + magic_string

        ac = base64.b64encode(hashlib.sha1(value.encode('utf-8')).digest())
        response_str = response_tpl % (ac.decode('utf-8'), headers.get("Host"))
        conn.sendall(bytes(response_str, encoding="utf-8"))
        t = threading.Thread(target=handler_msg, args=(conn, ))
        t.start()


def handler_msg(conn):
    with conn as c:
        data_recv = c.recv(1024)
        while True:
            try:
                AreaName = ""
                time.sleep(2)
                if data_recv[0:1] == b"\x81":
                    data_parse = parse_payload(data_recv)
                    AreaName = str(data_parse)
                data_dict = {}
                dir = {}
                pool = redis.ConnectionPool(host=constant.REDIS_HOST)
                redis_conn = redis.Redis(connection_pool=pool)
                areas = db_session.query(AreaTable).filter().all()
                area_list = []
                Tags = db_session.query(TagDetail).filter().all()
                i = 0
                for area in areas:
                    i = i + 1
                    Tags = db_session.query(TagDetail).filter(TagDetail.AreaName == area.AreaName).all()
                    areaSFlow = 0.0
                    areaSSum = 0.0
                    areaWFlow = 0.0
                    areaWSum = 0.0
                    areaEZGL = 0.0
                    areaEAI = 0.0
                    areaEAU = 0.0
                    areaEBI = 0.0
                    areaEBU = 0.0
                    areaECI = 0.0
                    areaECU = 0.0
                    area_dir = {}
                    for tag in Tags:
                        try:
                            S = str(tag.TagClassValue)[0:1]
                            if S == "S":
                                areaSFlow = areaSFlow + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                           tag.TagClassValue + "F"))
                                areaSSum = areaSSum + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                          tag.TagClassValue + "S"))
                            elif S == "W":
                                areaWFlow = areaWFlow + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                           tag.TagClassValue + "F"))
                                areaWSum = areaWSum + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                          tag.TagClassValue + "S"))
                            elif S == "E":
                                areaEZGL = areaEZGL + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                          tag.TagClassValue + "_ZGL"))
                                areaEAU = areaEAU + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                         tag.TagClassValue + "_AU"))
                                areaEAI = areaEAI + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                         tag.TagClassValue + "_AI"))
                                areaEBI = areaEBI + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                         tag.TagClassValue + "_BU"))
                                areaEBU = areaEBU + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                         tag.TagClassValue + "_BI"))
                                areaECI = areaECI + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                         tag.TagClassValue + "_CU"))
                                areaECU = areaECU + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                         tag.TagClassValue + "_CI"))
                        except Exception as ee:
                            print("报错tag：" + tag.TagClassValue + " |报错IP：" + tag.IP + "  |报错端口：" + tag.COMNum + "  |错误：" + str(ee))
                        finally:
                            pass
                    area_dir["AreaName"] = area.AreaName
                    area_dir["areaSFlow"] = areaSFlow
                    area_dir["areaSSum"] = areaSSum
                    area_dir["areaWFlow"] = areaWFlow
                    area_dir["areaWSum"] = areaWSum
                    area_dir["areaEZGL"] = areaEZGL
                    area_dir["areaEAI"] = areaEAI
                    area_dir["areaEAU"] = areaEAU
                    area_dir["areaEBI"] = areaEBI
                    area_dir["areaEBU"] = areaEBU
                    area_dir["areaECI"] = areaEBI
                    area_dir["areaECU"] = areaEBU
                    if i == 1:
                        areaSFlowT = 0.0
                        areaSSumT = 0.0
                        areaWFlowT = 0.0
                        areaWSumT = 0.0
                        areaEZGLT = 0.0
                        areaEAIT = 0.0
                        areaEAUT = 0.0
                        areaEBIT = 0.0
                        areaEBUT = 0.0
                        areaECIT = 0.0
                        areaECUT = 0.0
                        Tags = db_session.query(TagDetail).filter().all()
                        for tag in Tags:
                            try:
                                S = str(tag.TagClassValue)[0:1]
                                if S == "S":
                                    areaSFlowT = areaSFlowT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                     tag.TagClassValue + "F"))
                                    areaSSumT = areaSSumT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                   tag.TagClassValue + "S"))
                                elif S == "W":
                                    areaWFlowT = areaWFlowT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                       tag.TagClassValue + "F"))
                                    areaWSumT = areaWSumT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                     tag.TagClassValue + "S"))
                                elif S == "E":
                                    areaEZGLT = areaEZGLT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                     tag.TagClassValue + "_ZGL"))
                                    areaEAUT = areaEAUT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                   tag.TagClassValue + "_AU"))
                                    areaEAIT = areaEAIT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                   tag.TagClassValue + "_AI"))
                                    areaEBIT = areaEBIT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                   tag.TagClassValue + "_BU"))
                                    areaEBUT = areaEBUT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                   tag.TagClassValue + "_BI"))
                                    areaECIT = areaECIT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                   tag.TagClassValue + "_CU"))
                                    areaECUT = areaECUT + strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                                                                                   tag.TagClassValue + "_CI"))
                            except Exception as ee:
                                print(
                                    "报错tag：" + tag.TagClassValue + " |报错IP：" + tag.IP + "  |报错端口：" + tag.COMNum + "  |错误：" + str(
                                        ee))
                            finally:
                                pass
                        area_dir["AreaName"] = ""
                        area_dir["areaSFlow"] = areaSFlowT
                        area_dir["areaSSum"] = areaSSumT
                        area_dir["areaWFlow"] = areaWFlowT
                        area_dir["areaWSum"] = areaWSumT
                        area_dir["areaEZGL"] = areaEZGLT
                        area_dir["areaEAI"] = areaEAIT
                        area_dir["areaEAU"] = areaEAUT
                        area_dir["areaEBI"] = areaEBIT
                        area_dir["areaEBU"] = areaEBUT
                        area_dir["areaECI"] = areaEBIT
                        area_dir["areaECU"] = areaEBUT
                    area_list.append(area_dir)
                # i = 0
                # for tag in Tags:
                #     try:
                #         S = str(tag.TagClassValue)[0:1]
                #         if S == "S":
                #             tis_i={}
                #             tis_i["title"] = tag.FEFportIP
                #             tis_i["WD"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                      tag.TagClassValue + "WD"))
                #             tis_i["Flow"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                        tag.TagClassValue + "F"))
                #             tis_i["Sum"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                       tag.TagClassValue + "S"))
                #             dis.append(tis_i)
                #         elif S == "W":
                #             tiw_i = {}
                #             tiw_i["title"] = tag.FEFportIP
                #             tiw_i["Flow"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                        tag.TagClassValue + "F"))
                #             tiw_i["Sum"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                       tag.TagClassValue + "S"))
                #             diw.append(tiw_i)
                #         elif S == "E":
                #             tie_i = {}
                #             tie_i["title"] = tag.FEFportIP
                #             tie_i["ZGL"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                       tag.TagClassValue + "_ZGL"))
                #             tie_i["AU"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                      tag.TagClassValue + "_AU"))
                #             tie_i["AI"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                      tag.TagClassValue + "_AI"))
                #             tie_i["BU"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                      tag.TagClassValue + "_BU"))
                #             tie_i["BI"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                      tag.TagClassValue + "_BI"))
                #             tie_i["CU"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                      tag.TagClassValue + "_CU"))
                #             tie_i["CI"] = strtofloat(redis_conn.hget(constant.REDIS_TABLENAME,
                #                                                      tag.TagClassValue + "_CI"))
                #             die.append(tie_i)
                #     except Exception as ee:
                #         print("报错tag：" + tag.TagClassValue + " |报错IP：" + tag.IP + "  |报错端口：" + tag.COMNum + "  |错误：" + str(ee))
                #     finally:
                #         i = i + 1
                #         pass
                json_data = json.dumps(area_list)
                # bytemsg = bytes(json_data, encoding="utf8")
                # send_msg(c, bytes("recv: {}".format(data_parse), encoding="utf-8"))
                bytemsg = bytes(json_data,encoding="utf-8")
                send_msg(conn, bytemsg)
            except Exception as e:
                print(e)
            finally:
                pass
def strtofloat(f):
    if f == None or f == "" or f == b'':
        return 0.0
    else:
        return round(float(f), 2)


def server_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 5002))
    sock.listen(2)
    t = threading.Thread(target=handler_accept(sock))
    t.start()


if __name__ == "__main__":
    server_socket()
