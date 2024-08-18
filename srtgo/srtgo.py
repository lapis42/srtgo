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
from SRT.seat_type import SeatType
from SRT.passenger import Adult
from SRT.constants import STATION_CODE
from SRT.errors import SRTResponseError
from korail2 import Korail
from korail2 import AdultPassenger, ReserveOption
from korail2 import SoldOutError


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
            6: lambda: set_station(rail_type)
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


def get_telegram() -> Optional[Callable[[str], Awaitable[None]]]:
    token = keyring.get_password("telegram", "token")
    chat_id = keyring.get_password("telegram", "chat_id")

    async def tgprintf(text):
        if token and chat_id:
            bot = telegram.Bot(token=token)
            async with bot:
                await bot.send_message(chat_id=chat_id, text=text)

    return tgprintf


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
        inquirer.Password("birthday", message="생년월일 (YYMMDD, Enter: 완료, Ctrl-C: 취소)", default=card_info["birthday"]),
        inquirer.Password("expire", message="카드 유효기간 (YYMM, Enter: 완료, Ctrl-C: 취소)", default=card_info["expire"])
    ])
    if card_info:
        for key, value in card_info.items():
            keyring.set_password("card", key, value)
        keyring.set_password("card", "ok", "1")


def pay_card(rail, reservation) -> bool:
    if keyring.get_password("card", "ok"):
        return rail.pay_with_card(
            reservation,
            keyring.get_password("card", "number"),
            keyring.get_password("card", "password"),
            keyring.get_password("card", "birthday"),
            keyring.get_password("card", "expire"),
            0,
            "J"
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
        SRT(login_info["id"], login_info["pass"]) if rail_type == "SRT" else Korail(
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
    
    rail = SRT if rail_type == "SRT" else Korail
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

    stations, station_key = get_station(rail_type)

    q_info = [
        inquirer.List("departure", message="출발역 선택", choices=[stations[i] for i in station_key], default=default_departure),
        inquirer.List("arrival", message="도착역 선택", choices=[stations[i] for i in station_key], default=default_arrival),
        inquirer.List("date", message="출발 날짜 선택", choices=[((now + timedelta(days=i)).strftime("%Y/%m/%d %a"), (now + timedelta(days=i)).strftime("%Y%m%d")) for i in range(28)], default=default_date),
        inquirer.List("time", message="출발 시각 선택", choices=[(f"{h:02d}", f"{h:02d}0000") for h in range(0, 24, 2)], default=default_time[:2]),
        inquirer.List("passenger", message="승객수", choices=range(1, 10), default=default_passenger),
    ]
    info = inquirer.prompt(q_info)
    if info is None or info["departure"] == info["arrival"]:
        print(colored("출발역과 도착역이 같거나 선택되지 않았습니다", "green", "on_red") + "\n")
        return

    for key, value in info.items():
        keyring.set_password(rail_type, key, str(value))

    if info["date"] == today and int(info["time"]) < int(this_time):
        info["time"] = this_time

    # choose trains
    def search_train(rail, rail_type, info):
        search_params = {
            "dep": info["departure"],
            "arr": info["arrival"],
            "date": info["date"],
            "time": info["time"],
        }
        
        if rail_type == "SRT":
            search_params.update({
                "available_only": False,
                "passengers": [Adult(info["passenger"])],
                "search_all": False,
            })
        else:
            search_params.update({
                "passengers": [AdultPassenger(info["passenger"])],
                "include_no_seats": True,
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
        inquirer.Checkbox("trains", message="예약할 열차 선택", choices=[(train.__repr__(), i) for i, train in enumerate(trains)], default=list(range(min(6, len(trains))))),
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
            reserve = rail.reserve(train, passengers=[Adult(info["passenger"])], special_seat=choice["type"])
            msg = f"{reserve}\n" + "\n".join(str(ticket) for ticket in reserve.tickets)
            print(colored(f"\n\n\n🎊예매 성공!!!🎊\n{msg}", "red", "on_green"))
            
            if choice["pay"] and pay_card(rail, reserve):
                print(colored("🎊결제 성공!!!🎊", "green", "on_red"), end="")
            print(colored("\n\n", "red", "on_green"))
        else:
            reserve = rail.reserve(train, [AdultPassenger(info["passenger"])], choice["type"])
            msg = str(reserve)
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

                for i, train in enumerate(trains):
                    if i in choice["trains"] and _is_seat_available(train, choice["type"], rail_type):
                        _reserve(train)
                        return
            else:
                _reserve(train)
                return

            time.sleep(gammavariate(RESERVE_INTERVAL_SHAPE, RESERVE_INTERVAL_SCALE))
        except (SRTResponseError, SoldOutError):
            time.sleep(gammavariate(RESERVE_INTERVAL_SHAPE, RESERVE_INTERVAL_SCALE))
        except Exception as ex:
            print(f"\n{ex}\n")
            if not inquirer.confirm(message="계속할까요", default=True):
                return


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


if __name__ == "__main__":
    srtgo()