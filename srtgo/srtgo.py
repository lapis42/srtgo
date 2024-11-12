import asyncio
import time
from datetime import datetime, timedelta
from random import gammavariate
from typing import Optional, List, Union, Tuple, Callable, Awaitable

import click
import inquirer
import keyring
import telegram
from termcolor import colored

from SRT import SRT
from SRT import constants
from SRT.train import SRTTrain
from SRT.seat_type import SeatType
from SRT.passenger import Passenger, Adult, Child, Senior, Disability1To3, Disability4To6
from SRT.response_data import SRTResponseData
from SRT.reservation import SRTReservation, SRTTicket
from SRT.errors import SRTResponseError, SRTNotLoggedInError

from korail2 import Korail
from korail2 import AdultPassenger, ChildPassenger, SeniorPassenger, ReserveOption
from korail2 import Passenger as KorailPassenger
from korail2 import TrainType
from korail2 import KorailError


STATIONS = {
    "SRT": [
        "수서", "동탄", "평택지제", "곡성", "공주", "광주송정", "구례구", "김천(구미)", 
        "나주", "남원", "대전", "동대구", "마산", "목포", "밀양", "부산", "서대구", 
        "순천", "신경주", "여수EXPO", "여천", "오송", "울산(통도사)", "익산", "전주",
        "정읍", "진영", "진주", "창원", "천안아산", "포항"
    ],
    "KTX": [
        "서울", "용산", "영등포", "광명", "수원", "천안아산", "오송", "대전", "서대전", 
        "김천구미", "동대구", "경주", "포항", "밀양", "구포", "부산", "울산(통도사)", 
        "마산", "창원중앙", "경산", "논산", "익산", "정읍", "광주송정", "목포",
        "전주", "순천", "여수EXPO(구,여수역)", "청량리", "강릉", "행신", "정동진"
    ]
}
DEFAULT_STATIONS = {
    "SRT": [0, 1, 2, 10, 11, 15],
    "KTX": [0, 6, 7, 10, 15]
}

# 예약 간격 (평균 간격 (초) = SHAPE * SCALE)
RESERVE_INTERVAL_SHAPE = 4
RESERVE_INTERVAL_SCALE = 0.25

WAITING_BAR = ["|", "/", "-", "\\"]

RailType = Union[str, None]
ChoiceType = Union[int, None]


class Disability1To3Passenger(KorailPassenger):
    def __init__(self, count=1, discount_type='111', card='', card_no='', card_pw=''):
        KorailPassenger.__init_internal__(self, '1', count, discount_type, card, card_no, card_pw)   

class Disability4To6Passenger(KorailPassenger):
    def __init__(self, count=1, discount_type='112', card='', card_no='', card_pw=''):
        KorailPassenger.__init_internal__(self, '1', count, discount_type, card, card_no, card_pw)   


@click.command()
def srtgo():
    while True:
        choice = prompt_menu()
        if choice == -1:
            break

        rail_type = get_rail_type(choice)
        if rail_type is None and choice in [1, 2, 3, 6]:
            continue

        actions = {
            1: lambda: reserve(rail_type),
            2: lambda: check_reservation(rail_type),
            3: lambda: set_login(rail_type),
            4: set_telegram,
            5: set_card,
            6: lambda: set_station(rail_type),
            7: set_options
        }
        action = actions.get(choice)
        if action:
            action()


def prompt_menu() -> ChoiceType:
    choices = [
        ("예매 시작", 1),
        ("예매 확인/취소", 2),
        ("로그인 설정", 3),
        ("텔레그램 설정", 4),
        ("카드 설정", 5),
        ("역 설정", 6),
        ("예매 옵션 설정", 7),
        ("나가기", -1),
    ]
    return inquirer.list_input(message="메뉴 선택 (↕:이동, Enter: 선택)", choices=choices)


def get_rail_type(choice: int) -> Optional[str]:
    if choice not in [1, 2, 3, 6]:
        return None

    return inquirer.list_input(
        message="열차 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)",
        choices=[(colored("SRT", "red"), "SRT"), (colored("KTX", "cyan"), "KTX"), ("취소", -1)]
    )


def set_station(rail_type: RailType) -> bool:
    stations, default_station_key = get_station(rail_type)
    station_info = inquirer.prompt([
        inquirer.Checkbox(
            "stations",
            message="역 선택 (↕:이동, Space: 선택, Enter: 완료, Ctrl-A: 전체선택, Ctrl-R: 선택해제, Ctrl-C: 취소)",
            choices=[(station, i) for i, station in enumerate(stations)],
            default=default_station_key
        )
    ])

    if station_info is None:
        return False

    selected_stations = station_info.get('stations', [])
    if not selected_stations:
        print("선택된 역이 없습니다.")
        return False

    keyring.set_password(rail_type, "station", ','.join(map(str, selected_stations)))
    
    selected_station_names = ', '.join([stations[i] for i in selected_stations])
    print(f"선택된 역: {selected_station_names}")
    
    return True


def get_station(rail_type: RailType) -> Tuple[List[str], List[int]]:
    station_key = keyring.get_password(rail_type, "station")
    station_key = [int(x) for x in station_key.split(',')] if station_key else None

    stations = STATIONS[rail_type]
    default_stations = DEFAULT_STATIONS[rail_type]
    
    return stations, station_key or default_stations


def set_options():
    default_options = get_options()
    choices = inquirer.prompt([
        inquirer.Checkbox(
            "options",
            message="예매 옵션 선택 (Space: 선택, Enter: 완료, Ctrl-A: 전체선택, Ctrl-R: 선택해제, Ctrl-C: 취소)",
            choices=[
                ("어린이", "child"),
                ("경로우대", "senior"),
                ("중증장애인", "disability1to3"),
                ("경증장애인", "disability4to6"),
                ("KTX만", "ktx")
            ],
            default=default_options
        )
    ])

    if choices is None:
        return
    
    options = choices.get("options", [])
    keyring.set_password("SRT", "options", ','.join(options))


def get_options():
    options = keyring.get_password("SRT", "options") or ""
    return options.split(',') if options else []


def set_telegram() -> bool:
    token = keyring.get_password("telegram", "token") or ""
    chat_id = keyring.get_password("telegram", "chat_id") or ""

    telegram_info = inquirer.prompt([
        inquirer.Text("token", message="텔레그램 token (Enter: 완료, Ctrl-C: 취소)", default=token),
        inquirer.Text("chat_id", message="텔레그램 chat_id (Enter: 완료, Ctrl-C: 취소)", default=chat_id)
    ])
    if not telegram_info:
        return False

    token, chat_id = telegram_info["token"], telegram_info["chat_id"]

    try:
        keyring.set_password("telegram", "ok", "1")
        keyring.set_password("telegram", "token", token)
        keyring.set_password("telegram", "chat_id", chat_id)
        tgprintf = get_telegram()
        asyncio.run(tgprintf("[SRTGO] 텔레그램 설정 완료"))
        return True
    except Exception as err:
        print(err)
        keyring.delete_password("telegram", "ok")
        return False


def get_telegram() -> Optional[Callable[[str], Awaitable[None]]]:
    token = keyring.get_password("telegram", "token")
    chat_id = keyring.get_password("telegram", "chat_id")

    async def tgprintf(text):
        if token and chat_id:
            bot = telegram.Bot(token=token)
            async with bot:
                await bot.send_message(chat_id=chat_id, text=text)

    return tgprintf


def set_card() -> None:
    card_info = {
        "number": keyring.get_password("card", "number") or "",
        "password": keyring.get_password("card", "password") or "",
        "birthday": keyring.get_password("card", "birthday") or "",
        "expire": keyring.get_password("card", "expire") or ""
    }

    card_info = inquirer.prompt([
        inquirer.Password("number", message="신용카드 번호 (하이픈 제외(-), Enter: 완료, Ctrl-C: 취소)", default=card_info["number"]),
        inquirer.Password("password", message="카드 비밀번호 앞 2자리 (Enter: 완료, Ctrl-C: 취소)", default=card_info["password"]),
        inquirer.Password("birthday", message="생년월일 (YYMMDD) / 사업자등록번호 (Enter: 완료, Ctrl-C: 취소)", default=card_info["birthday"]),
        inquirer.Password("expire", message="카드 유효기간 (YYMM, Enter: 완료, Ctrl-C: 취소)", default=card_info["expire"])
    ])
    if card_info:
        for key, value in card_info.items():
            keyring.set_password("card", key, value)
        keyring.set_password("card", "ok", "1")


def pay_card(rail, reservation) -> bool:
    if keyring.get_password("card", "ok"):
        birthday = keyring.get_password("card", "birthday")
        return rail.pay_with_card(
            reservation,
            keyring.get_password("card", "number"),
            keyring.get_password("card", "password"),
            birthday,
            keyring.get_password("card", "expire"),
            0,
            "J" if len(birthday) == 6 else "S"
        )
    return False


def set_login(rail_type="SRT"):
    credentials = {
        "id": keyring.get_password(rail_type, "id") or "",
        "pass": keyring.get_password(rail_type, "pass") or ""
    }

    login_info = inquirer.prompt([
        inquirer.Text("id", message=f"{rail_type} 계정 아이디 (멤버십 번호, 이메일, 전화번호)", default=credentials["id"]),
        inquirer.Password("pass", message=f"{rail_type} 계정 패스워드", default=credentials["pass"])
    ])
    if not login_info:
        return False

    try:
        SRT2(login_info["id"], login_info["pass"]) if rail_type == "SRT" else Korail(
            login_info["id"], login_info["pass"])
        
        keyring.set_password(rail_type, "id", login_info["id"])
        keyring.set_password(rail_type, "pass", login_info["pass"])
        keyring.set_password(rail_type, "ok", "1")
        return True
    except SRTResponseError as err:
        print(err)
        keyring.delete_password(rail_type, "ok")
        return False


def login(rail_type="SRT"):
    if keyring.get_password(rail_type, "id") is None or keyring.get_password(rail_type, "pass") is None:
        set_login(rail_type)
    
    user_id = keyring.get_password(rail_type, "id")
    password = keyring.get_password(rail_type, "pass")
    
    rail = SRT2 if rail_type == "SRT" else Korail
    return rail(user_id, password)


def reserve(rail_type="SRT"):
    rail = login(rail_type)

    # Default values and prompts for user input
    now = datetime.now() + timedelta(minutes=10)
    today = now.strftime("%Y%m%d")
    this_time = now.strftime("%H%M%S")

    default_departure = keyring.get_password(rail_type, "departure") or ("수서" if rail_type == "SRT" else "서울")
    default_arrival = keyring.get_password(rail_type, "arrival") or "동대구"
    if default_departure == default_arrival:
        default_arrival = "동대구" if default_departure in ("수서", "서울") else None
        default_departure = default_departure if default_arrival else ("수서" if rail_type == "SRT" else "서울")

    default_date = keyring.get_password(rail_type, "date") or today
    default_time = keyring.get_password(rail_type, "time") or "120000"
    default_passenger = int(keyring.get_password(rail_type, "passenger") or 1)
    default_child = int(keyring.get_password(rail_type, "child") or 0)
    default_senior = int(keyring.get_password(rail_type, "senior") or 0)
    default_disability1to3 = int(keyring.get_password(rail_type, "disability1to3") or 0)
    default_disability4to6 = int(keyring.get_password(rail_type, "disability4to6") or 0)

    stations, station_key = get_station(rail_type)
    options = get_options()

    q_info = [
        inquirer.List("departure", message="출발역 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=[stations[i] for i in station_key], default=default_departure),
        inquirer.List("arrival", message="도착역 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=[stations[i] for i in station_key], default=default_arrival),
        inquirer.List("date", message="출발 날짜 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=[((now + timedelta(days=i)).strftime("%Y/%m/%d %a"), (now + timedelta(days=i)).strftime("%Y%m%d")) for i in range(28)], default=default_date),
        inquirer.List("time", message="출발 시각 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=[(f"{h:02d}", f"{h:02d}0000") for h in range(0, 24)], default=default_time),
        inquirer.List("passenger", message="성인 승객수 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=range(0, 10), default=default_passenger),
    ]
    if "child" in options:
        q_info.append(inquirer.List("child", message="어린이 승객수 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=range(0, 10), default=default_child))
    if "senior" in options:
        q_info.append(inquirer.List("senior", message="경로우대 승객수 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=range(0, 10), default=default_senior))
    if "disability1to3" in options:
        q_info.append(inquirer.List("disability1to3", message="1~3급 장애인 승객수 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=range(0, 10), default=default_disability1to3))
    if "disability4to6" in options:
        q_info.append(inquirer.List("disability4to6", message="4~6급 장애인 승객수 (↕:이동, Enter: 선택, Ctrl-C: 취소)", choices=range(0, 10), default=default_disability4to6))
    
    info = inquirer.prompt(q_info)

    if info is None:
        print(colored("예매 정보 입력 중 취소되었습니다", "green", "on_red") + "\n")
        return

    if info["departure"] == info["arrival"]:
        print(colored("출발역과 도착역이 같습니다", "green", "on_red") + "\n")
        return

    for key, value in info.items():
        keyring.set_password(rail_type, key, str(value))

    if info["date"] == today and int(info["time"]) < int(this_time):
        info["time"] = this_time

    passengers = []
    if info["passenger"] > 0:
        passengers.append((Adult if rail_type == "SRT" else AdultPassenger)(info["passenger"]))
    if "child" in options and info["child"] > 0:
        passengers.append((Child if rail_type == "SRT" else ChildPassenger)(info["child"]))
    if "senior" in options and info["senior"] > 0:
        passengers.append((Senior if rail_type == "SRT" else SeniorPassenger)(info["senior"]))
    if "disability1to3" in options and info["disability1to3"] > 0:
        passengers.append((Disability1To3 if rail_type == "SRT" else Disability1To3Passenger)(info["disability1to3"]))
    if "disability4to6" in options and info["disability4to6"] > 0:
        passengers.append((Disability4To6 if rail_type == "SRT" else Disability4To6Passenger)(info["disability4to6"]))
    
    if len(passengers) == 0:
        print(colored("승객수는 0이 될 수 없습니다", "green", "on_red") + "\n")
        return
    
    PASSENGER_TYPE = {
        Adult if rail_type == "SRT" else AdultPassenger: '어른/청소년',
        Child if rail_type == "SRT" else ChildPassenger: '어린이',
        Senior if rail_type == "SRT" else SeniorPassenger: '경로우대',
        Disability1To3 if rail_type == "SRT" else Disability1To3Passenger: '1~3급 장애인',
        Disability4To6 if rail_type == "SRT" else Disability4To6Passenger: '4~6급 장애인',
    }
    msg_passengers = [f'{PASSENGER_TYPE[type(passenger)]} {passenger.count}명' for passenger in passengers]
    print(*msg_passengers)
    
    # choose trains
    def search_train(rail, rail_type, info):
        search_params = {
            "dep": info["departure"],
            "arr": info["arrival"],
            "date": info["date"],
            "time": info["time"],
            "passengers": [Adult(len(passengers)) if rail_type == "SRT" else AdultPassenger(len(passengers))],
        }
        
        if rail_type == "SRT":
            search_params.update({
                "available_only": False,
            })
        else:
            search_params.update({
                "include_no_seats": True,
            })
            if "ktx" in options:
                search_params.update({
                    "train_type": TrainType.KTX,
                })

        return rail.search_train(**search_params)

    try:
        trains = search_train(rail, rail_type, info)
    except Exception as err:
        print(colored("예약 가능한 열차가 없습니다", "green", "on_red") + "\n")
        return

    if not trains:
        print(colored("예약 가능한 열차가 없습니다", "green", "on_red") + "\n")
        return

    seat_type = SeatType if rail_type == "SRT" else ReserveOption

    q_choice = [
        inquirer.Checkbox("trains", message="예약할 열차 선택 (↕:이동, Space: 선택, Enter: 완료, Ctrl-A: 전체선택, Ctrl-R: 선택해제, Ctrl-C: 취소)", choices=[(train.__repr__(), i) for i, train in enumerate(trains)], default=None),
        inquirer.List("type", message="선택 유형", choices=[("일반실 우선", seat_type.GENERAL_FIRST), ("일반실만", seat_type.GENERAL_ONLY), ("특실 우선", seat_type.SPECIAL_FIRST), ("특실만", seat_type.SPECIAL_ONLY)]),
    ]
    if rail_type == "SRT":
        q_choice.append(inquirer.Confirm("pay", message="예매 시 카드 결제", default=False))
    
    choice = inquirer.prompt(q_choice)
    if choice is None or not choice["trains"]:
        print(colored("선택한 열차가 없습니다!", "green", "on_red") + "\n")
        return

    do_search = len(choice["trains"]) > 1
    train = trains[choice["trains"][0]] if not do_search else None

    def _reserve(train):
        tgprintf = get_telegram()

        if rail_type == "SRT":
            reserve = rail.reserve(train, passengers=passengers, special_seat=choice["type"])
            msg = f"{reserve}\n" + "\n".join(str(ticket) for ticket in reserve.tickets)
            print(colored(f"\n\n\n🎊예매 성공!!!🎊\n{msg}", "red", "on_green"))
            
            if choice["pay"] and pay_card(rail, reserve):
                print(colored("🎊결제 성공!!!🎊", "green", "on_red"), end="")
            print(colored("\n\n", "red", "on_green"))
        else:
            reserve = rail.reserve(train, passengers=passengers, option=choice["type"])
            msg = str(reserve).strip()
            print(colored(f"\n\n\n🎊예매 성공!!!🎊\n{msg}\n\n", "red", "on_green"))
        
        asyncio.run(tgprintf(msg))

    i_try = 0
    start_time = time.time()
    while True:
        try:
            i_try += 1
            elapsed_time = time.time() - start_time
            print(f"\r예매 대기 중... {WAITING_BAR[i_try % len(WAITING_BAR)]} {i_try:4d} ({int(elapsed_time//3600):02d}:{int(elapsed_time%3600//60):02d}:{int(elapsed_time%60):02d})", end="", flush=True)

            if do_search:
                trains = search_train(rail, rail_type, info)
                for i in choice["trains"]:
                    if _is_seat_available(trains[i], choice["type"], rail_type):
                        _reserve(trains[i])
                        return
            else:
                _reserve(train)
                return

            time.sleep(gammavariate(RESERVE_INTERVAL_SHAPE, RESERVE_INTERVAL_SCALE))
        
        except (SRTResponseError, KorailError) as ex:
            if not ex.msg.startswith(("잔여석없음", "사용자가 많아 접속이 원활하지 않습니다", "Sold out")):
                if not _handle_error(ex):
                    return
            time.sleep(gammavariate(RESERVE_INTERVAL_SHAPE, RESERVE_INTERVAL_SCALE))

        except Exception as ex:
            if not _handle_error(ex):
                return
            time.sleep(gammavariate(RESERVE_INTERVAL_SHAPE, RESERVE_INTERVAL_SCALE))

def _handle_error(ex):
    msg = f"\nException: {ex}, Type: {type(ex)}, Args: {ex.args}, Message: {ex.msg if hasattr(ex, 'msg') else 'No message attribute'}"
    print(msg)
    tgprintf = get_telegram()
    asyncio.run(tgprintf(msg))
    return inquirer.confirm(message="계속할까요", default=True)

def _is_seat_available(train, seat_type, rail_type):
    if rail_type == "SRT":
        return (seat_type in [SeatType.GENERAL_FIRST, SeatType.SPECIAL_FIRST] and train.seat_available()) or \
               (seat_type == SeatType.GENERAL_ONLY and train.general_seat_available()) or \
               (seat_type == SeatType.SPECIAL_ONLY and train.special_seat_available())
    else:
        return (seat_type in [ReserveOption.GENERAL_FIRST, ReserveOption.SPECIAL_FIRST] and train.has_seat()) or \
               (seat_type == ReserveOption.GENERAL_ONLY and train.has_general_seat()) or \
               (seat_type == ReserveOption.SPECIAL_ONLY and train.has_special_seat())


def check_reservation(rail_type="SRT"):
    rail = login(rail_type)

    while True:
        reservations = rail.get_reservations() if rail_type == "SRT" else rail.reservations()
        tickets = [] if rail_type == "SRT" else rail.tickets()

        if not reservations and not tickets:
            print(colored("예약 내역이 없습니다", "green", "on_red") + "\n")
            return

        if tickets:
            print("[ 발권 내역 ]\n" + "\n".join(map(str, tickets)) + "\n")

        cancel_choices = [
            (str(reservation), i) for i, reservation in enumerate(reservations)
        ] + [("텔레그램으로 예매 정보 전송", -2), ("돌아가기", -1)]
        
        cancel = inquirer.list_input(
            message="예약 취소 (Enter: 결정)",
            choices=cancel_choices
        )

        if cancel in (None, -1):
            return

        if cancel == -2:
            out = []
            if tickets:
                out.append("[ 발권 내역 ]\n" + "\n".join(map(str, tickets)))
            if reservations:
                out.append("[ 예매 내역 ]")
                for reservation in reservations:
                    out.append(f"🚅{reservation}")
                    if rail_type == "SRT":
                        out.extend(map(str, reservation.tickets))
            
            if out:
                tgprintf = get_telegram()
                asyncio.run(tgprintf("\n".join(out)))
            return

        if inquirer.confirm(message=colored("정말 취소하시겠습니까", "green", "on_red")):
            try:
                rail.cancel(reservations[cancel])
            except Exception as err:
                print(err)
            return

class SRTTicket2(SRTTicket):
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
        "206": "4~6급 장애인",
    }
    
    def __init__(self, data):
        self.car = data["scarNo"]
        self.seat = data["seatNo"]
        self.seat_type_code = data["psrmClCd"]
        self.seat_type = self.SEAT_TYPE[self.seat_type_code]
        self.passenger_type_code = data["dcntKndCd"]
        if self.passenger_type_code in self.DISCOUNT_TYPE:
            self.passenger_type = self.DISCOUNT_TYPE[self.passenger_type_code]
        else:
            self.passenger_type = '기타 할인'

        self.price = int(data["rcvdAmt"])
        self.original_price = int(data["stdrPrc"])
        self.discount = int(data["dcntPrc"])

class SRT2(SRT): 
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
        """주어진 출발지에서 도착지로 향하는 SRT 열차를 검색합니다.

        Args:
            dep (str): 출발역
            arr (str): 도착역
            date (str, optional): 출발 날짜 (yyyyMMdd) (default: 당일)
            time (str, optional): 출발 시각 (hhmmss) (default: 0시 0분 0초)
            time_limit (str, optional): 출발 시각 조회 한도 (hhmmss)
            passengers (list[:class:`Passenger`], optional): 예약 인원 (default: 어른 1명)
            available_only (bool, optional): 매진되지 않은 열차만 검색합니다 (default: True)

        Returns:
            list[:class:`SRTTrain`]: 열차 리스트
        """

        if dep not in constants.STATION_CODE or arr not in constants.STATION_CODE:
            raise ValueError(f'Invalid station: "{dep}" or "{arr}"')

        dep_code, arr_code = constants.STATION_CODE[dep], constants.STATION_CODE[arr]
        date = date or datetime.now().strftime("%Y%m%d")
        time = time or "000000"

        passengers = passengers or [Adult()]
        passengers = Passenger.combine(passengers)
        passengers_count = str(Passenger.total_count(passengers))

        data = {
            "chtnDvCd": "1",
            "arriveTime": "N",
            "seatAttCd": "015",
            "psgNum": passengers_count,
            "trnGpCd": 109,
            "stlbTrnClsfCd": "05",
            "dptDt": date,
            "dptTm": time,
            "arvRsStnCd": arr_code,
            "dptRsStnCd": dep_code,
        }

        r = self._session.post(url=constants.API_ENDPOINTS["search_schedule"], data=data)
        parser = SRTResponseData(r.text)

        if not parser.success():
            raise SRTResponseError(parser.message())

        self._log(parser.message())
        all_trains = parser.get_all()["outDataSets"]["dsOutput1"]
        trains = [SRTTrain(train) for train in all_trains]
        trains = [train for train in trains if train.train_name == 'SRT']

        if available_only:
            trains = [t for t in trains if t.seat_available()]

        if time_limit:
            trains = [t for t in trains if t.dep_time <= time_limit]

        return trains
    
    def ticket_info(self, reservation: SRTReservation | int) -> list[SRTTicket2]:
        if not self.is_login:
            raise SRTNotLoggedInError()

        if isinstance(reservation, SRTReservation):
            reservation = reservation.reservation_number

        url = constants.API_ENDPOINTS["ticket_info"]
        data = {"pnrNo": reservation, "jrnySqno": "1"}

        r = self._session.post(url=url, data=data)
        parser = SRTResponseData(r.text)

        if not parser.success():
            raise SRTResponseError(parser.message())

        tickets = [SRTTicket2(ticket) for ticket in parser.get_all()["trainListMap"]]

        return tickets


if __name__ == "__main__":
    srtgo()