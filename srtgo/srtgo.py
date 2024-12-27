from datetime import datetime, timedelta
from json.decoder import JSONDecodeError
from random import gammavariate
from requests.exceptions import ConnectionError
from termcolor import colored
from typing import Awaitable, Callable, List, Optional, Tuple, Union

import asyncio
import click
import inquirer
import keyring
import telegram
import time

from .ktx import (
    Korail,
    KorailError,
    ReserveOption,
    TrainType,
    AdultPassenger,
    ChildPassenger, 
    SeniorPassenger,
    Disability1To3Passenger,
    Disability4To6Passenger
)

from .srt import (
    SRT,
    SRTError,
    SeatType,
    Adult,
    Child,
    Senior,
    Disability1To3,
    Disability4To6
)


STATIONS = {
    "SRT": [
        "수서", "동탄", "평택지제", "경주", "곡성", "공주", "광주송정", "구례구", "김천(구미)",
        "나주", "남원", "대전", "동대구", "마산", "목포", "밀양", "부산", "서대구",
        "순천", "여수EXPO", "여천", "오송", "울산(통도사)", "익산", "전주",
        "정읍", "진영", "진주", "창원", "창원중앙", "천안아산", "포항"
    ],
    "KTX": [
        "서울", "용산", "영등포", "광명", "수원", "천안아산", "오송", "대전", "서대전",
        "김천구미", "동대구", "경주", "포항", "밀양", "구포", "부산", "울산(통도사)",
        "마산", "창원중앙", "경산", "논산", "익산", "정읍", "광주송정", "목포",
        "전주", "순천", "여수EXPO", "청량리", "강릉", "행신", "정동진"
    ]
}
DEFAULT_STATIONS = {
    "SRT": [0, 11, 12, 16],
    "KTX": [0, 7, 10, 15]
}

# 예약 간격 (평균 간격 (초) = SHAPE * SCALE)
RESERVE_INTERVAL_SHAPE = 5
RESERVE_INTERVAL_SCALE = 0.25

WAITING_BAR = ["|", "/", "-", "\\"]

RailType = Union[str, None]
ChoiceType = Union[int, None]


@click.command()
@click.option("--debug", is_flag=True, help="Debug mode")
def srtgo(debug=False):
    MENU_CHOICES = [
        ("예매 시작", 1),
        ("예매 확인/취소", 2),
        ("로그인 설정", 3), 
        ("텔레그램 설정", 4),
        ("카드 설정", 5),
        ("역 설정", 6),
        ("예매 옵션 설정", 7),
        ("나가기", -1)
    ]

    RAIL_CHOICES = [
        (colored("SRT", "red"), "SRT"),
        (colored("KTX", "cyan"), "KTX"),
        ("취소", -1)
    ]

    ACTIONS = {
        1: lambda rt: reserve(rt, debug),
        2: lambda rt: check_reservation(rt, debug),
        3: lambda rt: set_login(rt, debug),
        4: lambda _: set_telegram(),
        5: lambda _: set_card(),
        6: set_station,
        7: lambda _: set_options()
    }

    while True:
        choice = inquirer.list_input(message="메뉴 선택 (↕:이동, Enter: 선택)", choices=MENU_CHOICES)
        
        if choice == -1:
            break

        if choice in {1, 2, 3, 6}:
            rail_type = inquirer.list_input(
                message="열차 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)",
                choices=RAIL_CHOICES
            )
            if rail_type in {-1, None}:
                continue
        else:
            rail_type = None

        action = ACTIONS.get(choice)
        if action:
            action(rail_type)


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
    stations = STATIONS[rail_type]
    station_key = keyring.get_password(rail_type, "station")
    
    if not station_key:
        return stations, DEFAULT_STATIONS[rail_type]
        
    valid_keys = [int(x) for x in station_key.split(',') if int(x) < len(stations)]
    return stations, valid_keys or DEFAULT_STATIONS[rail_type]


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


def set_login(rail_type="SRT", debug=False):
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
        SRT(login_info["id"], login_info["pass"], verbose=debug) if rail_type == "SRT" else Korail(
            login_info["id"], login_info["pass"], verbose=debug)
        
        keyring.set_password(rail_type, "id", login_info["id"])
        keyring.set_password(rail_type, "pass", login_info["pass"])
        keyring.set_password(rail_type, "ok", "1")
        return True
    except SRTError as err:
        print(err)
        keyring.delete_password(rail_type, "ok")
        return False


def login(rail_type="SRT", debug=False):
    if keyring.get_password(rail_type, "id") is None or keyring.get_password(rail_type, "pass") is None:
        set_login(rail_type)
    
    user_id = keyring.get_password(rail_type, "id")
    password = keyring.get_password(rail_type, "pass")
    
    rail = SRT if rail_type == "SRT" else Korail
    return rail(user_id, password, verbose=debug)


def reserve(rail_type="SRT", debug=False):
    rail = login(rail_type, debug=debug)
    is_srt = rail_type == "SRT"

    # Get date, time, stations, and passenger info
    now = datetime.now() + timedelta(minutes=10)
    today = now.strftime("%Y%m%d")
    this_time = now.strftime("%H%M%S")

    defaults = {
        "departure": keyring.get_password(rail_type, "departure") or ("수서" if is_srt else "서울"),
        "arrival": keyring.get_password(rail_type, "arrival") or "동대구",
        "date": keyring.get_password(rail_type, "date") or today,
        "time": keyring.get_password(rail_type, "time") or "120000",
        "adult": int(keyring.get_password(rail_type, "adult") or 1),
        "child": int(keyring.get_password(rail_type, "child") or 0),
        "senior": int(keyring.get_password(rail_type, "senior") or 0),
        "disability1to3": int(keyring.get_password(rail_type, "disability1to3") or 0),
        "disability4to6": int(keyring.get_password(rail_type, "disability4to6") or 0)
    }

    # Set default stations if departure equals arrival
    if defaults["departure"] == defaults["arrival"]:
        defaults["arrival"] = "동대구" if defaults["departure"] in ("수서", "서울") else None
        defaults["departure"] = defaults["departure"] if defaults["arrival"] else ("수서" if is_srt else "서울")

    stations, station_key = get_station(rail_type)
    options = get_options()
    station_choices = [stations[i] for i in station_key]
    
    # Generate date and time choices
    date_choices = [((now + timedelta(days=i)).strftime("%Y/%m/%d %a"), 
                    (now + timedelta(days=i)).strftime("%Y%m%d")) for i in range(28)]
    time_choices = [(f"{h:02d}", f"{h:02d}0000") for h in range(24)]

    # Build inquirer questions
    q_info = [
        inquirer.List("departure", message="출발역 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)", 
                     choices=station_choices, default=defaults["departure"]),
        inquirer.List("arrival", message="도착역 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)", 
                     choices=station_choices, default=defaults["arrival"]),
        inquirer.List("date", message="출발 날짜 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)", 
                     choices=date_choices, default=defaults["date"]),
        inquirer.List("time", message="출발 시각 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소)", 
                     choices=time_choices, default=defaults["time"]),
        inquirer.List("adult", message="성인 승객수 (↕:이동, Enter: 선택, Ctrl-C: 취소)", 
                     choices=range(10), default=defaults["adult"]),
    ]

    passenger_types = {
        "child": "어린이",
        "senior": "경로우대", 
        "disability1to3": "1~3급 장애인",
        "disability4to6": "4~6급 장애인"
    }

    passenger_classes = {
        "adult": Adult if is_srt else AdultPassenger,
        "child": Child if is_srt else ChildPassenger,
        "senior": Senior if is_srt else SeniorPassenger,
        "disability1to3": Disability1To3 if is_srt else Disability1To3Passenger,
        "disability4to6": Disability4To6 if is_srt else Disability4To6Passenger
    }

    PASSENGER_TYPE = {
        passenger_classes["adult"]: '어른/청소년',
        passenger_classes["child"]: '어린이',
        passenger_classes["senior"]: '경로우대',
        passenger_classes["disability1to3"]: '1~3급 장애인',
        passenger_classes["disability4to6"]: '4~6급 장애인',
    }

    # Add passenger type questions if enabled in options
    for key, label in passenger_types.items():
        if key in options:
            q_info.append(inquirer.List(key, 
                message=f"{label} 승객수 (↕:이동, Enter: 선택, Ctrl-C: 취소)",
                choices=range(10), default=defaults[key]))

    info = inquirer.prompt(q_info)

    # Validate input info
    if not info:
        print(colored("예매 정보 입력 중 취소되었습니다", "green", "on_red") + "\n")
        return

    if info["departure"] == info["arrival"]:
        print(colored("출발역과 도착역이 같습니다", "green", "on_red") + "\n")
        return

    # Save preferences
    for key, value in info.items():
        keyring.set_password(rail_type, key, str(value))

    # Adjust time if needed
    if info["date"] == today and int(info["time"]) < int(this_time):
        info["time"] = this_time

    # Build passenger list
    passengers = []
    total_count = 0
    for key, cls in passenger_classes.items():
        if key in info and info[key] > 0:
            passengers.append(cls(info[key]))
            total_count += info[key]

    # Validate passenger count
    if not passengers:
        print(colored("승객수는 0이 될 수 없습니다", "green", "on_red") + "\n")
        return

    if total_count >= 10:
        print(colored("승객수는 10명을 초과할 수 없습니다", "green", "on_red") + "\n")
        return

    msg_passengers = [f'{PASSENGER_TYPE[type(passenger)]} {passenger.count}명' for passenger in passengers]
    print(*msg_passengers)

    # Search for trains
    params = {
        "dep": info["departure"],
        "arr": info["arrival"], 
        "date": info["date"],
        "time": info["time"],
        "passengers": [passenger_classes["adult"](total_count)],
        **({"available_only": False} if is_srt else {
            "include_no_seats": True,
            **({"train_type": TrainType.KTX} if "ktx" in options else {})
        })
    }

    trains = rail.search_train(**params)

    def train_decorator(train):
        msg = train.__repr__()
        return msg.replace('예약가능', colored('가능', "green")) \
                 .replace('가능', colored('가능', "green")) \
                 .replace('신청하기', colored('가능', "green"))

    if not trains:
        print(colored("예약 가능한 열차가 없습니다", "green", "on_red") + "\n")
        return

    # Get train selection
    q_choice = [
        inquirer.Checkbox("trains", message="예약할 열차 선택 (↕:이동, Space: 선택, Enter: 완료, Ctrl-A: 전체선택, Ctrl-R: 선택해제, Ctrl-C: 취소)", 
                         choices=[(train_decorator(train), i) for i, train in enumerate(trains)], default=None),
    ]
    
    choice = inquirer.prompt(q_choice)
    if choice is None or not choice["trains"]:
        print(colored("선택한 열차가 없습니다!", "green", "on_red") + "\n")
        return
    
    n_trains = len(choice["trains"])

    # Get seat type preference
    seat_type = SeatType if is_srt else ReserveOption
    q_choice = []
    if n_trains > 1:
        do_search = True
        q_choice.append(inquirer.List("type", message="선택 유형", 
                                    choices=[("일반실 우선", seat_type.GENERAL_FIRST), 
                                            ("일반실만", seat_type.GENERAL_ONLY),
                                            ("특실 우선", seat_type.SPECIAL_FIRST), 
                                            ("특실만", seat_type.SPECIAL_ONLY)]))
    else:
        train = trains[choice["trains"][0]]
        is_waiting_available = (
            (is_srt and not train.seat_available() and train.reserve_wait_possible_code >= 0) or
            (not is_srt and not train.has_seat() and train.wait_reserve_flag >= 0)
        )
        do_search = is_waiting_available
        q_choice.append(inquirer.List("type", message="선택 유형", 
                                    choices=[("일반실만", seat_type.GENERAL_ONLY),
                                            ("특실만", seat_type.SPECIAL_ONLY)]))
    q_choice.append(inquirer.Confirm("pay", message="예매 시 카드 결제", default=False))

    options = inquirer.prompt(q_choice)
    if options is None:
        print(colored("예매 정보 입력 중 취소되었습니다", "green", "on_red") + "\n")
        return

    # Reserve function
    def _reserve(train):
        reserve = rail.reserve(train, passengers=passengers, option=options["type"])
        msg = (f"{reserve}\n" + "\n".join(str(ticket) for ticket in reserve.tickets)) if is_srt else str(reserve).strip()

        print(colored(f"\n\n🎫 🎉 예매 성공!!! 🎉 🎫\n{msg}\n", "red", "on_green"))

        if options["pay"] and not reserve.is_waiting and pay_card(rail, reserve):
            print(colored("\n\n💳 ✨ 결제 성공!!! ✨ 💳\n\n", "green", "on_red"), end="")
            msg += "\n결제 완료"

        tgprintf = get_telegram()
        asyncio.run(tgprintf(msg))

    # Reservation loop
    i_try = 0
    start_time = time.time()
    while True:
        try:
            trains = rail.search_train(**params)
            while True:
                i_try += 1
                elapsed_time = time.time() - start_time
                hours, remainder = divmod(int(elapsed_time), 3600)
                minutes, seconds = divmod(remainder, 60)
                print(f"\r예매 대기 중... {WAITING_BAR[i_try & 3]} {i_try:4d} ({hours:02d}:{minutes:02d}:{seconds:02d}) ",
                    end="", flush=True)

                if do_search:
                    trains = rail.search_train(**params)
                    for i in choice["trains"]:
                        train = trains[i]
                        if _is_seat_available(train, options["type"], rail_type):
                            _reserve(train)
                            return
                else:
                    _reserve(train)
                    return
                _sleep()

        except SRTError as ex:
            msg = ex.msg
            if "정상적인 경로로 접근 부탁드립니다" in msg:
                if debug:
                    error_msg = f"\nException: {ex}\nType: {type(ex)}\nArgs: {ex.args}\nMessage: {msg}"
                    print(error_msg)
                rail.clear()
            elif "로그인 후 사용하십시오" in msg:
                if debug:
                    error_msg = f"\nException: {ex}\nType: {type(ex)}\nArgs: {ex.args}\nMessage: {msg}"
                    print(error_msg)
                rail.is_login = False
                rail.login()
                if not rail.is_login:
                    if not _handle_error(ex):
                        return
            elif not any(err in msg for err in (
                "잔여석없음",
                "사용자가 많아 접속이 원활하지 않습니다",
                "예약대기 접수가 마감되었습니다",
                "예약대기자한도수초과"
            )):
                if not _handle_error(ex):
                    return
            _sleep()

        except KorailError as ex:
            if not any(msg in str(ex) for msg in ("Sold out", "잔여석없음", "예약대기자한도수초과")) and not _handle_error(ex):
                return
            _sleep()

        except JSONDecodeError as ex:
            if debug:
                error_msg = f"\nException: {ex}\nType: {type(ex)}\nArgs: {ex.args}\nMessage: {ex.msg}"
                print(error_msg)
            _sleep()
        
        except ConnectionError as ex:
            if not _handle_error(ex, "연결이 끊겼습니다"):
                return

        except Exception as ex:
            if debug:
                print("\nUndefined exception")
            if not _handle_error(ex):
                return

def _sleep():
    time.sleep(gammavariate(RESERVE_INTERVAL_SHAPE, RESERVE_INTERVAL_SCALE))

def _handle_error(ex, msg=None):
    msg = msg or f"\nException: {ex}, Type: {type(ex)}, Message: {ex.msg if hasattr(ex, 'msg') else 'No message attribute'}"
    print(msg)
    tgprintf = get_telegram()
    asyncio.run(tgprintf(msg))
    return inquirer.confirm(message="계속할까요", default=True)

def _is_seat_available(train, seat_type, rail_type):
    if rail_type == "SRT":
        if not train.seat_available():
            return train.reserve_standby_available()
        if seat_type in [SeatType.GENERAL_FIRST, SeatType.SPECIAL_FIRST]:
            return train.seat_available()
        if seat_type == SeatType.GENERAL_ONLY:
            return train.general_seat_available()
        return train.special_seat_available()
    else:
        if not train.has_seat():
            return train.has_waiting_list()
        if seat_type in [ReserveOption.GENERAL_FIRST, ReserveOption.SPECIAL_FIRST]:
            return train.has_seat()
        if seat_type == ReserveOption.GENERAL_ONLY:
            return train.has_general_seat()
        return train.has_special_seat()


def check_reservation(rail_type="SRT", debug=False):
    rail = login(rail_type, debug=debug)

    while True:
        reservations = rail.get_reservations() if rail_type == "SRT" else rail.reservations()
        tickets = [] if rail_type == "SRT" else rail.tickets()

        all_reservations = []
        for t in tickets:
            t.is_ticket = True
            all_reservations.append(t)
        for r in reservations:
            if hasattr(r, "paid") and r.paid:
                r.is_ticket = True
            else:
                r.is_ticket = False
            all_reservations.append(r)

        if not reservations and not tickets:
            print(colored("예약 내역이 없습니다", "green", "on_red") + "\n")
            return

        cancel_choices = [
            (str(reservation), i) for i, reservation in enumerate(all_reservations)
        ] + [("텔레그램으로 예매 정보 전송", -2), ("돌아가기", -1)]
        
        cancel = inquirer.list_input(
            message="예약 취소 (Enter: 결정)",
            choices=cancel_choices
        )

        if cancel in (None, -1):
            return

        if cancel == -2:
            out = []
            if all_reservations:
                out.append("[ 예매 내역 ]")
                for reservation in all_reservations:
                    out.append(f"🚅{reservation}")
                    if rail_type == "SRT":
                        out.extend(map(str, reservation.tickets))
            
            if out:
                tgprintf = get_telegram()
                asyncio.run(tgprintf("\n".join(out)))
            return

        if inquirer.confirm(message=colored("정말 취소하시겠습니까", "green", "on_red")):
            try:
                if all_reservations[cancel].is_ticket:
                    rail.refund(all_reservations[cancel])
                else:
                    rail.cancel(all_reservations[cancel])
            except Exception as err:
                raise err
            return


if __name__ == "__main__":
    srtgo()