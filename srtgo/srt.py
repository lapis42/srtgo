import abc
import json
import re
import requests
import time
from enum import Enum
from datetime import datetime
from typing import Dict, List, Pattern

# Constants
EMAIL_REGEX: Pattern = re.compile(r"[^@]+@[^@]+\.[^@]+")
PHONE_NUMBER_REGEX: Pattern = re.compile(r"(\d{3})-(\d{3,4})-(\d{4})")

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14; SM-S911U1 Build/UP1A.231005.007; wv) AppleWebKit/537.36"
    "(KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36SRT-APP-Android V.2.0.32"
)

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

RESERVE_JOBID = {
    "PERSONAL": "1101",  # 개인예약
    "STANDBY": "1102",  # 예약대기
}

STATION_CODE = {
    "수서": "0551",
    "동탄": "0552", 
    "평택지제": "0553",
    "경주": "0508",
    "곡성": "0049",
    "공주": "0514",
    "광주송정": "0036",
    "구례구": "0050",
    "김천(구미)": "0507",
    "나주": "0037",
    "남원": "0048",
    "대전": "0010",
    "동대구": "0015",
    "마산": "0059",
    "목포": "0041",
    "밀양": "0017",
    "부산": "0020",
    "서대구": "0506",
    "순천": "0051",
    "여수EXPO": "0053",
    "여천": "0139",
    "오송": "0297",
    "울산(통도사)": "0509",
    "익산": "0030",
    "전주": "0045",
    "정읍": "0033",
    "진영": "0056",
    "진주": "0063",
    "창원": "0057",
    "창원중앙": "0512",
    "천안아산": "0502",
    "포항": "0515",
}

STATION_NAME = {code: name for name, code in STATION_CODE.items()}

TRAIN_NAME = {
    "00": "KTX",
    "02": "무궁화",
    "03": "통근열차", 
    "04": "누리로",
    "05": "전체",
    "07": "KTX-산천",
    "08": "ITX-새마을",
    "09": "ITX-청춘",
    "10": "KTX-산천",
    "17": "SRT",
    "18": "ITX-마음",
}

WINDOW_SEAT = {None: "000", True: "012", False: "013"}

SRT_MOBILE = "https://app.srail.or.kr:443"
API_ENDPOINTS = {
    "main": f"{SRT_MOBILE}/main/main.do",
    "login": f"{SRT_MOBILE}/apb/selectListApb01080_n.do",
    "logout": f"{SRT_MOBILE}/login/loginOut.do", 
    "search_schedule": f"{SRT_MOBILE}/ara/selectListAra10007_n.do",
    "reserve": f"{SRT_MOBILE}/arc/selectListArc05013_n.do",
    "tickets": f"{SRT_MOBILE}/atc/selectListAtc14016_n.do",
    "ticket_info": f"{SRT_MOBILE}/ard/selectListArd02019_n.do",
    "cancel": f"{SRT_MOBILE}/ard/selectListArd02045_n.do",
    "standby_option": f"{SRT_MOBILE}/ata/selectListAta01135_n.do",
    "payment": f"{SRT_MOBILE}/ata/selectListAta09036_n.do",
    "reserve_info": f"{SRT_MOBILE}/atc/getListAtc14087.do",
    "reserve_info_referer": f"{SRT_MOBILE}/common/ATC/ATC0201L/view.do?pnrNo=",
    "refund": f"{SRT_MOBILE}/atc/selectListAtc02063_n.do",
}


# Exception classes
class SRTError(Exception):
    def __init__(self, msg):
        super().__init__(msg)
        self.msg = msg

    def __str__(self):
        return self.msg

class SRTLoginError(SRTError):
    pass

class SRTResponseError(SRTError):
    pass

class SRTDuplicateError(SRTResponseError):
    pass

class SRTNotLoggedInError(SRTError):
    pass

class SRTNetFunnelError(SRTError):
    pass


# Passenger class
class Passenger(metaclass=abc.ABCMeta):
    """Base class for different passenger types."""

    @abc.abstractmethod
    def __init__(self):
        pass

    def __init_internal__(self, name: str, type_code: str, count: int):
        self.name = name
        self.type_code = type_code
        self.count = count

    def __repr__(self) -> str:
        return f"{self.name} {self.count}명"

    def __add__(self, other: "Passenger") -> "Passenger":
        if not isinstance(other, self.__class__):
            raise TypeError("Passenger types must be the same")
        if self.type_code == other.type_code:
            return self.__class__(count=self.count + other.count)
        raise ValueError("Passenger types must be the same")

    @classmethod
    def combine(cls, passengers: List["Passenger"]) -> List["Passenger"]:
        if not all(isinstance(p, Passenger) for p in passengers):
            raise TypeError("All passengers must be based on Passenger")

        passenger_dict = {}
        for passenger in passengers:
            key = passenger.__class__
            passenger_dict[key] = passenger_dict.get(key, passenger.__class__(0)) + passenger

        return [p for p in passenger_dict.values() if p.count > 0]

    @staticmethod
    def total_count(passengers: List["Passenger"]) -> str:
        if not all(isinstance(p, Passenger) for p in passengers):
            raise TypeError("All passengers must be based on Passenger")
        return str(sum(p.count for p in passengers))

    @staticmethod
    def get_passenger_dict(
        passengers: List["Passenger"],
        special_seat: bool = False,
        window_seat: str = None
    ) -> Dict[str, str]:
        if not all(isinstance(p, Passenger) for p in passengers):
            raise TypeError("All passengers must be instances of Passenger")

        combined_passengers = Passenger.combine(passengers)
        data = {
            "totPrnb": Passenger.total_count(combined_passengers),
            "psgGridcnt": str(len(combined_passengers)),
            "locSeatAttCd1": WINDOW_SEAT.get(window_seat, "000"),
            "rqSeatAttCd1": "015",
            "dirSeatAttCd1": "009",
            "smkSeatAttCd1": "000",
            "etcSeatAttCd1": "000",
            "psrmClCd1": "2" if special_seat else "1"
        }

        for i, passenger in enumerate(combined_passengers, start=1):
            data[f"psgTpCd{i}"] = passenger.type_code
            data[f"psgInfoPerPrnb{i}"] = str(passenger.count)

        return data


class Adult(Passenger):
    def __init__(self, count: int = 1):
        super().__init__()
        super().__init_internal__("어른/청소년", "1", count)


class Child(Passenger):
    def __init__(self, count: int = 1):
        super().__init__()
        super().__init_internal__("어린이", "5", count)


class Senior(Passenger):
    def __init__(self, count: int = 1):
        super().__init__()
        super().__init_internal__("경로", "4", count)


class Disability1To3(Passenger):
    def __init__(self, count: int = 1):
        super().__init__()
        super().__init_internal__("장애 1~3급", "2", count)


class Disability4To6(Passenger):
    def __init__(self, count: int = 1):
        super().__init__()
        super().__init_internal__("장애 4~6급", "3", count)


# Ticket class
class SRTTicket:
    SEAT_TYPE = {"1": "일반실", "2": "특실"}

    PASSENGER_TYPE = {
        "1": "어른/청소년", 
        "2": "장애 1~3급",
        "3": "장애 4~6급",
        "4": "경로",
        "5": "어린이"
    }

    DISCOUNT_TYPE = {
        "000": "어른/청소년",
        "101": "탄력운임기준할인", 
        "105": "자유석 할인",
        "106": "입석 할인",
        "107": "역방향석 할인",
        "108": "출입구석 할인", 
        "109": "가족석 일반전환 할인",
        "111": "구간별 특정운임",
        "112": "열차별 특정운임",
        "113": "구간별 비율할인(기준)",
        "114": "열차별 비율할인(기준)",
        "121": "공항직결 수색연결운임",
        "131": "구간별 특별할인(기준)",
        "132": "열차별 특별할인(기준)", 
        "133": "기본 특별할인(기준)",
        "191": "정차역 할인",
        "192": "매체 할인",
        "201": "어린이",
        "202": "동반유아 할인",
        "204": "경로",
        "205": "1~3급 장애인",
        "206": "4~6급 장애인"
    }

    def __init__(self, data: dict) -> None:
        self.car = data.get("scarNo")
        self.seat = data.get("seatNo")
        self.seat_type_code = data.get("psrmClCd")
        self.seat_type = self.SEAT_TYPE[self.seat_type_code]
        self.passenger_type_code = data.get("dcntKndCd")
        self.passenger_type = self.DISCOUNT_TYPE.get(self.passenger_type_code, "기타 할인")
        self.price = int(data.get("rcvdAmt"))
        self.original_price = int(data.get("stdrPrc")) 
        self.discount = int(data.get("dcntPrc"))
        self.is_waiting = self.seat == ""

    def __str__(self) -> str:
        return self.dump()

    __repr__ = __str__

    def dump(self) -> str:
        if self.is_waiting:
            return (
                f"예약대기 ({self.seat_type}) {self.passenger_type}"
                f"[{self.price}원({self.discount}원 할인)]"
            )
        return (
            f"{self.car}호차 {self.seat} ({self.seat_type}) {self.passenger_type} "
            f"[{self.price}원({self.discount}원 할인)]"
        )


class SRTReservation:
    def __init__(self, train, pay, tickets):
        self.reservation_number = train.get("pnrNo")
        self.total_cost = int(train.get("rcvdAmt"))
        self.seat_count = train.get("tkSpecNum") or int(train.get("seatNum"))

        self.train_code = pay.get("stlbTrnClsfCd")
        self.train_name = TRAIN_NAME[self.train_code]
        self.train_number = pay.get("trnNo")

        self.dep_date = pay.get("dptDt")
        self.dep_time = pay.get("dptTm")
        self.dep_station_code = pay.get("dptRsStnCd")
        self.dep_station_name = STATION_NAME[self.dep_station_code]

        self.arr_time = pay.get("arvTm")
        self.arr_station_code = pay.get("arvRsStnCd")
        self.arr_station_name = STATION_NAME[self.arr_station_code]

        self.payment_date = pay.get("iseLmtDt")
        self.payment_time = pay.get("iseLmtTm")
        self.paid = pay.get("stlFlg") == "Y"
        self.is_running = "tkSpecNum" not in train
        self.is_waiting = not (self.paid or self.payment_date or self.payment_time)

        self._tickets = tickets

    def __str__(self):
        return self.dump()

    __repr__ = __str__

    def dump(self):
        base = (
            f"[{self.train_name}] "
            f"{self.dep_date[4:6]}월 {self.dep_date[6:8]}일, "
            f"{self.dep_station_name}~{self.arr_station_name}"
            f"({self.dep_time[:2]}:{self.dep_time[2:4]}~{self.arr_time[:2]}:{self.arr_time[2:4]}) "
            f"{self.total_cost}원({self.seat_count}석)"
        )

        if not self.paid:
            if not self.is_waiting:
                base += (
                    f", 구입기한 {self.payment_date[4:6]}월 {self.payment_date[6:8]}일 "
                    f"{self.payment_time[:2]}:{self.payment_time[2:4]}"
                )
            else:
                base += ", 예약대기"
        
        if self.is_running:
            base += f" (운행중)"

        return base

    @property
    def tickets(self):
        return self._tickets


# SRTResponseData class
class SRTResponseData:
    """SRT Response data class that parses JSON response from API request"""

    STATUS_SUCCESS = "SUCC"
    STATUS_FAIL = "FAIL"

    def __init__(self, response: str) -> None:
        self._json = json.loads(response)
        self._status = self._parse()

    def __str__(self) -> str:
        return json.dumps(self._json)

    dump = __str__  # Alias dump() to __str__()

    def _parse(self) -> dict:
        if "resultMap" in self._json:
            return self._json["resultMap"][0]

        if "ErrorCode" in self._json and "ErrorMsg" in self._json:
            raise SRTResponseError(
                f'Undefined result status "[{self._json["ErrorCode"]}]: {self._json["ErrorMsg"]}"'
            )
        raise SRTError(f"Unexpected case [{self._json}]")

    def success(self) -> bool:
        result = self._status.get("strResult")
        if result is None:
            raise SRTResponseError("Response status is not given")
        
        if result == self.STATUS_SUCCESS:
            return True
        if result == self.STATUS_FAIL:
            return False
        
        raise SRTResponseError(f'Undefined result status "{result}"')

    def message(self) -> str:
        return self._status.get("msgTxt", "")

    def get_all(self) -> dict:
        return self._json.copy()

    def get_status(self) -> dict:
        return self._status.copy()


class SeatType(Enum):
    GENERAL_FIRST = 1  # 일반실 우선
    GENERAL_ONLY = 2   # 일반실만 
    SPECIAL_FIRST = 3  # 특실 우선
    SPECIAL_ONLY = 4   # 특실만


# Train class
class Train:
    pass


class SRTTrain(Train):
    def __init__(self, data):
        self.train_code = data["stlbTrnClsfCd"]
        self.train_name = TRAIN_NAME[self.train_code]
        self.train_number = data["trnNo"]
        
        # Departure info
        self.dep_date = data["dptDt"]
        self.dep_time = data["dptTm"]
        self.dep_station_code = data["dptRsStnCd"]
        self.dep_station_name = STATION_NAME[self.dep_station_code]
        self.dep_station_run_order = data["dptStnRunOrdr"]
        self.dep_station_constitution_order = data["dptStnConsOrdr"]

        # Arrival info  
        self.arr_date = data["arvDt"]
        self.arr_time = data["arvTm"]
        self.arr_station_code = data["arvRsStnCd"]
        self.arr_station_name = STATION_NAME[self.arr_station_code]
        self.arr_station_run_order = data["arvStnRunOrdr"]
        self.arr_station_constitution_order = data["arvStnConsOrdr"]

        # Seat availability info
        self.general_seat_state = data["gnrmRsvPsbStr"]
        self.special_seat_state = data["sprmRsvPsbStr"]
        self.reserve_wait_possible_name = data["rsvWaitPsbCdNm"]
        self.reserve_wait_possible_code = int(data["rsvWaitPsbCd"]) # -1: 예약대기 없음, 9: 예약대기 가능, 0: 매진, -2: 예약대기 불가능

    def __str__(self):
        return self.dump()

    def __repr__(self):
        return self.dump()

    def dump(self):
        dep_hour, dep_min = self.dep_time[0:2], self.dep_time[2:4]
        arr_hour, arr_min = self.arr_time[0:2], self.arr_time[2:4]
        month, day = self.dep_date[4:6], self.dep_date[6:8]

        msg = (
            f"[{self.train_name} {self.train_number}] "
            f"{month}월 {day}일, "
            f"{self.dep_station_name}~{self.arr_station_name}"
            f"({dep_hour}:{dep_min}~{arr_hour}:{arr_min}) "
            f"특실 {self.special_seat_state}, 일반실 {self.general_seat_state}"
        )
        if self.reserve_wait_possible_code >= 0:
            msg += f", 예약대기 {self.reserve_wait_possible_name}"
        return msg

    def general_seat_available(self):
        return "예약가능" in self.general_seat_state

    def special_seat_available(self):
        return "예약가능" in self.special_seat_state

    def reserve_standby_available(self):
        return self.reserve_wait_possible_code == 9

    def seat_available(self):
        return self.general_seat_available() or self.special_seat_available()


# NetFunnel
class NetFunnelHelper:
    NETFUNNEL_URL = "http://nf.letskorail.com/ts.wseq"

    WAIT_STATUS_PASS = "200"
    WAIT_STATUS_FAIL = "201" 
    ALREADY_COMPLETED = "502"

    OP_CODE = {
        "getTidchkEnter": "5101",
        "chkEnter": "5002", 
        "setComplete": "5004",
    }

    DEFAULT_HEADERS = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "ko,en;q=0.9,en-US;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive", 
        "Pragma": "no-cache",
        "Referer": SRT_MOBILE,
        "Sec-Fetch-Dest": "script",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }

    def __init__(self, debug=False):
        self._session = requests.session()
        self._session.headers.update(self.DEFAULT_HEADERS)
        self._cached_key = None
        self._last_fetch_time = 0
        self._cache_ttl = 48  # 48 seconds
        self.debug = debug

    def run(self):
        current_time = time.time()
        if self._is_cache_valid(current_time):
            return self._cached_key

        try:
            status, self._cached_key, nwait = self._start()
            self._last_fetch_time = current_time

            while status == self.WAIT_STATUS_FAIL:
                print(f"\r현재 {nwait}명 대기중...", end="", flush=True)
                time.sleep(1)
                status, self._cached_key, nwait = self._check()
            
            # Try completing once
            status, _, _ = self._complete()
            if status == self.WAIT_STATUS_PASS or status == self.ALREADY_COMPLETED:
                return self._cached_key

            self.clear()
            raise SRTNetFunnelError("Failed to complete NetFunnel")

        except Exception as ex:
            self.clear()
            raise SRTNetFunnelError(str(ex))

    def clear(self):
        self._cached_key = None
        self._last_fetch_time = 0

    def _start(self):
        return self._make_request("getTidchkEnter")

    def _check(self):
        return self._make_request("chkEnter")

    def _complete(self):
        return self._make_request("setComplete")

    def _make_request(self, opcode: str):
        params = self._build_params(self.OP_CODE[opcode])
        r = self._session.get(self.NETFUNNEL_URL, params=params)
        if self.debug:
            print(r.text)
        response = self._parse(r.text)
        return response.get("status"), response.get("key"), response.get("nwait")

    def _build_params(self, opcode: str, timestamp: str = None, key: str = None) -> dict:
        params = {
            "opcode": opcode,
            "nfid": "0",
            "prefix": f"NetFunnel.gRtype={opcode};",
            "js": "true",
            str(int(time.time() * 1000) if timestamp is None else timestamp): ""
        }

        if opcode in (self.OP_CODE["getTidchkEnter"], self.OP_CODE["chkEnter"]):
            params.update({"sid": "service_1", "aid": "act_10"})
            if opcode == self.OP_CODE["chkEnter"]:
                params.update({"key": key or self._cached_key, "ttl": "1"})
        elif opcode == self.OP_CODE["setComplete"]:
            params["key"] = key or self._cached_key

        return params

    def _parse(self, response: str) -> dict:
        result_match = re.search(r"NetFunnel\.gControl\.result='([^']+)'", response)
        if not result_match:
            raise SRTNetFunnelError("Failed to parse NetFunnel response")

        code, status, params_str = result_match.group(1).split(":", 2)
        if not params_str:
            raise SRTNetFunnelError("Failed to parse NetFunnel response")

        params = dict(param.split("=", 1) for param in params_str.split("&") if "=" in param)
        params.update({"code": code, "status": status})
        return params

    def _is_cache_valid(self, current_time: float) -> bool:
        return bool(self._cached_key and (current_time - self._last_fetch_time) < self._cache_ttl)


# SRT class
class SRT:
    """SRT client class for interacting with the SRT train booking system.

    Args:
        srt_id (str): SRT account ID (membership number, email, or phone)
        srt_pw (str): SRT account password 
        auto_login (bool): Whether to automatically login on initialization
        verbose (bool): Whether to print debug logs

    Examples:
        >>> srt = SRT("1234567890", YOUR_PASSWORD) # with membership number
        >>> srt = SRT("def6488@gmail.com", YOUR_PASSWORD) # with email
        >>> srt = SRT("010-1234-xxxx", YOUR_PASSWORD) # with phone number
    """

    def __init__(
        self, srt_id: str, srt_pw: str, auto_login: bool = True, verbose: bool = False
    ) -> None:
        self._session = requests.session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._netfunnel = NetFunnelHelper(debug=verbose)
        self.srt_id = srt_id
        self.srt_pw = srt_pw
        self.verbose = verbose
        self.is_login = False
        self.membership_number = None
        self.membership_name = None
        self.phone_number = None

        if auto_login:
            self.login()

    def _log(self, msg: str) -> None:
        if self.verbose:
            print("[*] " + msg)

    def login(self, srt_id: str | None = None, srt_pw: str | None = None) -> bool:
        """Login to SRT server.

        Usually called automatically on initialization.

        Args:
            srt_id: Optional override of instance srt_id
            srt_pw: Optional override of instance srt_pw

        Returns:
            bool: Whether login was successful

        Raises:
            SRTLoginError: If login fails
        """
        srt_id = srt_id or self.srt_id
        srt_pw = srt_pw or self.srt_pw

        login_type = "2" if EMAIL_REGEX.match(srt_id) else (
            "3" if PHONE_NUMBER_REGEX.match(srt_id) else "1"
        )

        if login_type == "3":
            srt_id = re.sub("-", "", srt_id)

        data = {
            "auto": "Y",
            "check": "Y", 
            "page": "menu",
            "deviceKey": "-",
            "customerYn": "",
            "login_referer": API_ENDPOINTS["main"],
            "srchDvCd": login_type,
            "srchDvNm": srt_id,
            "hmpgPwdCphd": srt_pw,
        }

        r = self._session.post(url=API_ENDPOINTS["login"], data=data)
        self._log(r.text)

        if "존재하지않는 회원입니다" in r.text:
            raise SRTLoginError(r.json()["MSG"])
        if "비밀번호 오류" in r.text:
            raise SRTLoginError(r.json()["MSG"])
        if "Your IP Address Blocked" in r.text:
            raise SRTLoginError(r.text.strip())

        self.is_login = True
        user_info = json.loads(r.text)["userMap"]
        self.membership_number = user_info["MB_CRD_NO"]
        self.membership_name = user_info["CUST_NM"]
        self.phone_number = user_info["MBL_PHONE"]

        print(f"로그인 성공: {self.membership_name} (멤버십번호: {self.membership_number}, 전화번호: {self.phone_number})")
        return True

    def logout(self) -> bool:
        """Logout from SRT server.

        Returns:
            bool: Whether logout was successful

        Raises:
            SRTResponseError: If server returns error
        """
        if not self.is_login:
            return True

        r = self._session.post(url=API_ENDPOINTS["logout"])
        self._log(r.text)

        if not r.ok:
            raise SRTResponseError(r.text)

        self.is_login = False
        self.membership_number = None
        return True

    def search_train(
        self,
        dep: str,
        arr: str,
        date: str | None = None,
        time: str | None = None,
        time_limit: str | None = None,
        passengers: list[Passenger] | None = None,
        available_only: bool = True,
    ) -> list[SRTTrain]:
        """Search for available trains.

        Args:
            dep: Departure station name
            arr: Arrival station name
            date: Date in YYYYMMDD format (default: today)
            time: Time in HHMMSS format (default: 000000)
            time_limit: Only return trains before this time
            passengers: List of passengers (default: 1 adult)
            available_only: Only return trains with available seats

        Returns:
            List of matching SRTTrain objects

        Raises:
            ValueError: If invalid station names provided
        """
        if dep not in STATION_CODE or arr not in STATION_CODE:
            raise ValueError(f'Invalid station: "{dep}" or "{arr}"')

        now = datetime.now()
        today = now.strftime("%Y%m%d")
        date = date or today
        
        if date < today:
            raise ValueError("Date cannot be before today")
            
        time = (
            max(time or "000000", now.strftime("%H%M%S")) 
            if date == today
            else time or "000000"
        )

        passengers = Passenger.combine(passengers or [Adult()])

        data = {
            "chtnDvCd": "1",
            "dptDt": date,
            "dptTm": time,
            "dptDt1": date,
            "dptTm1": time[:2] + "0000",
            "dptRsStnCd": STATION_CODE[dep],
            "arvRsStnCd": STATION_CODE[arr],
            "stlbTrnClsfCd": "05",
            "trnGpCd": 109,
            "trnNo": "",
            "psgNum": str(Passenger.total_count(passengers)),
            "seatAttCd": "015", 
            "arriveTime": "N",
            "tkDptDt": "",
            "tkDptTm": "",
            "tkTrnNo": "",
            "tkTripChgFlg": "",
            "dlayTnumAplFlg": "Y",
            "netfunnelKey": self._netfunnel.run()
        }

        r = self._session.post(url=API_ENDPOINTS["search_schedule"], data=data)
        self._log(r.text)
        parser = SRTResponseData(r.text)

        if not parser.success():
            raise SRTResponseError(parser.message())

        return [
            train for train in (
                SRTTrain(t) for t in parser.get_all()["outDataSets"]["dsOutput1"] 
                if t["stlbTrnClsfCd"] == '17'
            )
            if (not available_only or train.seat_available()) and
               (not time_limit or train.dep_time <= time_limit)
        ]

    def reserve(
        self,
        train: SRTTrain,
        passengers: list[Passenger] | None = None,
        option: SeatType = SeatType.GENERAL_FIRST,
        window_seat: bool | None = None,
    ) -> SRTReservation:
        """Reserve a train.

        Args:
            train: Train to reserve
            passengers: List of passengers (default: 1 adult)
            option: Seat type preference
            window_seat: Whether to prefer window seats

        Returns:
            SRTReservation object for the reservation

        Examples:
            >>> trains = srt.search_train("수서", "부산", "210101", "000000")
            >>> srt.reserve(trains[0])
        """
        if not train.seat_available() and train.reserve_wait_possible_code >= 0:
            reservation = self.reserve_standby(train, passengers, option=option, mblPhone=self.phone_number)
            if self.phone_number:
                agree_class_change = option == SeatType.SPECIAL_FIRST or option == SeatType.GENERAL_FIRST
                self.reserve_standby_option_settings(reservation, isAgreeSMS=True, isAgreeClassChange=agree_class_change, telNo=self.phone_number)
            return reservation

        return self._reserve(
            RESERVE_JOBID["PERSONAL"],
            train,
            passengers,
            option,
            window_seat=window_seat,
        )

    def reserve_standby(
        self,
        train: SRTTrain,
        passengers: list[Passenger] | None = None,
        option: SeatType = SeatType.GENERAL_FIRST,
        mblPhone: str | None = None,
    ) -> SRTReservation:
        """Request waitlist reservation.

        Args:
            train: Train to waitlist
            passengers: List of passengers (default: 1 adult) 
            option: Seat type preference
            mblPhone: Phone number for notifications

        Returns:
            SRTReservation object for the waitlist

        Examples:
            >>> trains = srt.search_train("수서", "부산", "210101", "000000")
            >>> srt.reserve_standby(trains[0])
        """
        if option == SeatType.SPECIAL_FIRST:
            option = SeatType.SPECIAL_ONLY
        elif option == SeatType.GENERAL_FIRST:
            option = SeatType.GENERAL_ONLY
        return self._reserve(
            RESERVE_JOBID["STANDBY"],
            train,
            passengers,
            option,
            mblPhone=mblPhone
        )

    def _reserve(
        self,
        jobid: str,
        train: SRTTrain,
        passengers: list[Passenger] | None = None,
        option: SeatType = SeatType.GENERAL_FIRST,
        mblPhone: str | None = None,
        window_seat: bool | None = None,
    ) -> SRTReservation:
        """Common reservation request handler.

        Args:
            jobid: Type of reservation (personal/standby)
            train: Train to reserve
            passengers: List of passengers
            option: Seat type preference
            mblPhone: Phone number for standby notifications
            window_seat: Window seat preference for personal reservations

        Returns:
            SRTReservation object

        Raises:
            SRTNotLoggedInError: If not logged in
            TypeError: If train is not SRTTrain
            ValueError: If train is not SRT
            SRTError: If reservation not found after creation
        """
        if not self.is_login:
            raise SRTNotLoggedInError()

        if not isinstance(train, SRTTrain):
            raise TypeError('"train" must be SRTTrain instance')

        if train.train_name != "SRT":
            raise ValueError(f'Expected "SRT" train, got {train.train_name}')

        passengers = Passenger.combine(passengers or [Adult()])

        is_special_seat = {
            SeatType.GENERAL_ONLY: False,
            SeatType.SPECIAL_ONLY: True,
            SeatType.GENERAL_FIRST: not train.general_seat_available(),
            SeatType.SPECIAL_FIRST: train.special_seat_available()
        }[option]

        data = {
            "jobId": jobid,
            "jrnyCnt": "1",
            "jrnyTpCd": "11",
            "jrnySqno1": "001",
            "stndFlg": "N",
            "trnGpCd1": "300",
            "trnGpCd": "109",
            "grpDv": "0",
            "rtnDv": "0",
            "stlbTrnClsfCd1": train.train_code,
            "dptRsStnCd1": train.dep_station_code,
            "dptRsStnCdNm1": train.dep_station_name,
            "arvRsStnCd1": train.arr_station_code,
            "arvRsStnCdNm1": train.arr_station_name,
            "dptDt1": train.dep_date,
            "dptTm1": train.dep_time,
            "arvTm1": train.arr_time,
            "trnNo1": f"{int(train.train_number):05d}",
            "runDt1": train.dep_date,
            "dptStnConsOrdr1": train.dep_station_constitution_order,
            "arvStnConsOrdr1": train.arr_station_constitution_order,
            "dptStnRunOrdr1": train.dep_station_run_order,
            "arvStnRunOrdr1": train.arr_station_run_order,
            "mblPhone": mblPhone,
            "netfunnelKey": self._netfunnel.run()
        }

        if jobid == RESERVE_JOBID["PERSONAL"]:
            data["reserveType"] = "11"

        data.update(Passenger.get_passenger_dict(
            passengers, 
            special_seat=is_special_seat,
            window_seat=window_seat
        ))

        r = self._session.post(url=API_ENDPOINTS["reserve"], data=data)
        self._log(r.text)
        parser = SRTResponseData(r.text)

        if not parser.success():
            raise SRTResponseError(parser.message())

        reservation_number = parser.get_all()["reservListMap"][0]["pnrNo"]

        for ticket in self.get_reservations():
            if ticket.reservation_number == reservation_number:
                return ticket

        raise SRTError("Ticket not found: check reservation status")

    def reserve_standby_option_settings(
        self,
        reservation: SRTReservation | int,
        isAgreeSMS: bool,
        isAgreeClassChange: bool,
        telNo: str | None = None,
    ) -> bool:
        """Configure waitlist options.

        Args:
            reservation: Reservation object or number
            isAgreeSMS: Whether to receive SMS notifications
            isAgreeClassChange: Whether to accept seat class changes
            telNo: Phone number for notifications

        Returns:
            bool: Whether update was successful

        Examples:
            >>> trains = srt.search_train("수서", "부산", "210101", "000000")
            >>> res = srt.reserve_standby(trains[0])
            >>> srt.reserve_standby_option_settings(res, True, True, "010-1234-xxxx")
        """
        if not self.is_login:
            raise SRTNotLoggedInError()

        reservation_number = getattr(reservation, 'reservation_number', reservation)

        data = {
            "pnrNo": reservation_number,
            "psrmClChgFlg": "Y" if isAgreeClassChange else "N",
            "smsSndFlg": "Y" if isAgreeSMS else "N",
            "telNo": telNo if isAgreeSMS else "",
        }

        r = self._session.post(url=API_ENDPOINTS["standby_option"], data=data)
        self._log(r.text)
        return r.status_code == 200

    def get_reservations(self, paid_only: bool = False) -> list[SRTReservation]:
        """Get all reservations.

        Args:
            paid_only: Whether to only return paid reservations

        Returns:
            List of SRTReservation objects

        Raises:
            SRTNotLoggedInError: If not logged in
            SRTResponseError: If server returns error
        """
        if not self.is_login:
            raise SRTNotLoggedInError()

        r = self._session.post(url=API_ENDPOINTS["tickets"], data={"pageNo": "0"})
        self._log(r.text)
        parser = SRTResponseData(r.text)

        if not parser.success():
            raise SRTResponseError(parser.message())

        return [
            SRTReservation(train, pay, self.ticket_info(train["pnrNo"]))
            for train, pay in zip(
                parser.get_all()["trainListMap"],
                parser.get_all()["payListMap"]
            )
            if not paid_only or pay["stlFlg"] != "N"
        ]

    def ticket_info(self, reservation: SRTReservation | int) -> list[SRTTicket]:
        """Get detailed ticket information.

        Args:
            reservation: Reservation object or number

        Returns:
            List of SRTTicket objects

        Raises:
            SRTNotLoggedInError: If not logged in
            SRTResponseError: If server returns error
        """
        if not self.is_login:
            raise SRTNotLoggedInError()

        reservation_number = getattr(reservation, 'reservation_number', reservation)
        
        r = self._session.post(
            url=API_ENDPOINTS["ticket_info"],
            data={"pnrNo": reservation_number, "jrnySqno": "1"}
        )
        self._log(r.text)
        parser = SRTResponseData(r.text)

        if not parser.success():
            raise SRTResponseError(parser.message())

        return [SRTTicket(ticket) for ticket in parser.get_all()["trainListMap"]]

    def cancel(self, reservation: SRTReservation | int) -> bool:
        """Cancel a reservation.

        Args:
            reservation: Reservation object or number

        Returns:
            bool: Whether cancellation was successful

        Examples:
            >>> reservation = srt.reserve(train)
            >>> srt.cancel(reservation)
            >>> reservations = srt.get_reservations()
            >>> srt.cancel(reservations[0])

        Raises:
            SRTNotLoggedInError: If not logged in
            SRTResponseError: If server returns error
        """
        if not self.is_login:
            raise SRTNotLoggedInError()

        reservation_number = getattr(reservation, 'reservation_number', reservation)

        data = {
            "pnrNo": reservation_number,
            "jrnyCnt": "1",
            "rsvChgTno": "0"
        }

        r = self._session.post(url=API_ENDPOINTS["cancel"], data=data)
        self._log(r.text)
        parser = SRTResponseData(r.text)

        if not parser.success():
            raise SRTResponseError(parser.message())

        return True

    def pay_with_card(
        self,
        reservation: SRTReservation,
        number: str,
        password: str,
        validation_number: str,
        expire_date: str,
        installment: int = 0,
        card_type: str = "J",
    ) -> bool:
        """Pay for a reservation with credit card.

        Args:
            reservation: Reservation to pay for
            number: Card number (no hyphens)
            password: First 2 digits of card password
            validation_number: Birth date (card_type=J) or business number (card_type=S)
            expire_date: Card expiry date (YYMM)
            installment: Number of installments (0,2-12,24)
            card_type: Card type (J=personal, S=corporate)

        Returns:
            bool: Whether payment was successful

        Examples:
            >>> reservation = srt.reserve(train)
            >>> srt.pay_with_card(reservation, "1234567890123456", "12", "981204", "2309")

        Raises:
            SRTNotLoggedInError: If not logged in
            SRTResponseError: If payment fails
        """
        if not self.is_login:
            raise SRTNotLoggedInError()

        data = {
            "stlDmnDt": datetime.now().strftime("%Y%m%d"),
            "mbCrdNo": self.membership_number,
            "stlMnsSqno1": "1",
            "ststlGridcnt": "1",
            "totNewStlAmt": reservation.total_cost,
            "athnDvCd1": card_type,
            "vanPwd1": password,
            "crdVlidTrm1": expire_date,
            "stlMnsCd1": "02",
            "rsvChgTno": "0",
            "chgMcs": "0",
            "ismtMnthNum1": installment,
            "ctlDvCd": "3102",
            "cgPsId": "korail",
            "pnrNo": reservation.reservation_number,
            "totPrnb": reservation.seat_count,
            "mnsStlAmt1": reservation.total_cost,
            "crdInpWayCd1": "@",
            "athnVal1": validation_number,
            "stlCrCrdNo1": number,
            "jrnyCnt": "1",
            "strJobId": "3102",
            "inrecmnsGridcnt": "1",
            "dptTm": reservation.dep_time,
            "arvTm": reservation.arr_time,
            "dptStnConsOrdr2": "000000",
            "arvStnConsOrdr2": "000000",
            "trnGpCd": "300",
            "pageNo": "-",
            "rowCnt": "-",
            "pageUrl": "",
        }

        r = self._session.post(url=API_ENDPOINTS["payment"], data=data)
        self._log(r.text)
        response = json.loads(r.text)

        if response["outDataSets"]["dsOutput0"][0]["strResult"] == "FAIL":
            raise SRTResponseError(response["outDataSets"]["dsOutput0"][0]["msgTxt"])

        return True
    
    def reserve_info(self, reservation: SRTReservation | int) -> bool:
        referer = API_ENDPOINTS["reserve_info_referer"] + reservation.reservation_number
        self._session.headers.update({"Referer": referer})
        r = self._session.post(url=API_ENDPOINTS["reserve_info"])
        self._log(r.text)
        response = json.loads(r.text)
        if response.get("ErrorCode") == "0" and response.get("ErrorMsg") == "":
            return response.get("outDataSets").get("dsOutput1")[0]
        else:
            raise SRTResponseError(response.get("ErrorMsg"))
    
    def refund(self, reservation: SRTReservation | int) -> bool:
        info = self.reserve_info(reservation)
        data = {
            "pnr_no": info.get("pnrNo"),
            "cnc_dmn_cont": "승차권 환불로 취소",
            "saleDt": info.get("ogtkSaleDt"),
            "saleWctNo": info.get("ogtkSaleWctNo"),
            "saleSqno": info.get("ogtkSaleSqno"),
            "tkRetPwd": info.get("ogtkRetPwd"),
            "psgNm": info.get("buyPsNm"),
        }

        r = self._session.post(url=API_ENDPOINTS["refund"], data=data)
        self._log(r.text)
        response = SRTResponseData(r.text)

        if not response.success():
            raise SRTResponseError(response.message())

        return True
    
    def clear(self):
        self._log("Clearing the netfunnel key")
        self._netfunnel.clear()
