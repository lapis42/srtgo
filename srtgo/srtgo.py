import click
import inquirer
import keyring
import time
import telegram
import asyncio
from random import random
from termcolor import colored
from datetime import datetime, timedelta
from SRT import SRT
from SRT.seat_type import SeatType
from korail2 import Korail
from korail2 import AdultPassenger, ReserveOption


@click.command()
def srtgo():
    while True:
        menu = [
            inquirer.List(
                "menu",
                message="메뉴 선택 (↕:이동, Enter: 완료)",
                choices=[
                    (colored("SRT", "red") + " 예매 시작", 1),
                    (colored("KTX", "cyan") + " 예매 시작", 2),
                    (colored("SRT", "red") + " 예매 확인/취소", 3),
                    (colored("KTX", "cyan") + " 예매 확인/취소", 4),
                    (colored("SRT", "red") + " 로그인 설정", 5),
                    (colored("KTX", "cyan") + " 로그인 설정", 6),
                    ("텔레그램 설정", 7),
                    ("나가기", 8),
                ],
            )
        ]
        choice = inquirer.prompt(menu)

        if choice is None:
            return

        if choice["menu"] == 1:
            reserve("SRT")
        elif choice["menu"] == 2:
            reserve("KTX")
        elif choice["menu"] == 3:
            check_reservation("SRT")
        elif choice["menu"] == 4:
            check_reservation("KTX")
        elif choice["menu"] == 5:
            set_login("SRT")
        elif choice["menu"] == 6:
            set_login("KTX")
        elif choice["menu"] == 7:
            set_telegram()
        else:
            return


def set_telegram():
    # telegram
    if keyring.get_password("telegram", "ok") is not None:
        token = keyring.get_password("telegram", "token")
        chat_id = keyring.get_password("telegram", "chat_id")
    else:
        token = ""
        chat_id = ""

    q_telegram = [
        inquirer.Text(
            "token", message="텔레그램 token (Enter: 완료, Ctrl-C: 취소)", default=token
        ),
        inquirer.Text(
            "chat_id",
            message="텔레그램 chat_id (Enter: 완료, Ctrl-C: 취소)",
            default=chat_id,
        ),
    ]
    telegram_info = inquirer.prompt(q_telegram)
    if telegram_info is None:
        return False

    token = telegram_info["token"]
    chat_id = telegram_info["chat_id"]
    if not token or not chat_id:
        return False

    async def tgprintf(text):
        bot = telegram.Bot(token=token)
        async with bot:
            await bot.send_message(chat_id=chat_id, text=text)

    try:
        asyncio.run(tgprintf("[SRTGO] 텔레그램 설정 완료"))
        keyring.set_password("telegram", "ok", "1")
        keyring.set_password("telegram", "token", token)
        keyring.set_password("telegram", "chat_id", chat_id)
        return True
    except Exception as err:
        print(err)
        keyring.delete_password("telegram", "ok")
        return False


def get_telegram():
    if keyring.get_password("telegram", "ok") is not None:
        token = keyring.get_password("telegram", "token")
        chat_id = keyring.get_password("telegram", "chat_id")
    else:
        token = None
        chat_id = None

    async def tgprintf(text):
        if token and chat_id:
            bot = telegram.Bot(token=token)
            async with bot:
                await bot.send_message(chat_id=chat_id, text=text)

    return tgprintf


def set_login(rail_type="SRT"):
    if keyring.get_password(rail_type, "ok") is not None:
        id = keyring.get_password(rail_type, "id")
        password = keyring.get_password(rail_type, "pass")
    else:
        id = ""
        password = ""

    q_login = [
        inquirer.Text(
            "id",
            message=rail_type + " 계정 아이디 (멤버십 번호, 이메일, 전화번호)",
            default=id,
        ),
        inquirer.Text("pass", message=rail_type + " 계정 패스워드", default=password),
    ]
    login = inquirer.prompt(q_login)

    if login is None:
        return False

    id = login["id"]
    password = login["pass"]

    if id and password:
        keyring.set_password(rail_type, "id", id)
        keyring.set_password(rail_type, "pass", password)
    else:
        return False

    try:
        if rail_type == "SRT":
            SRT(id, password)
        else:
            Korail(id, password)
        keyring.set_password(rail_type, "ok", "1")
        return True
    except Exception as err:
        print(err)
        keyring.delete_password(rail_type, "ok")
        return False


def login(rail_type="SRT"):
    # login
    if keyring.get_password(rail_type, "ok") is None:
        set_login(rail_type)

    id = keyring.get_password(rail_type, "id")
    password = keyring.get_password(rail_type, "pass")
    if rail_type == "SRT":
        return SRT(id, password)
    else:
        return Korail(id, password)


def reserve(rail_type="SRT"):
    rail = login(rail_type)

    # 출발역 / 도착역 / 날짜 / 시각 선택
    default_departure = keyring.get_password(rail_type, "departure")
    if default_departure is None:
        if rail_type == "SRT":
            default_departure = "수서"
        else:
            default_departure = "서울"

    now = datetime.now() + timedelta(minutes=10)
    today = now.strftime("%Y%m%d")
    this_time = now.strftime("%H%M%S")

    default_arrival = keyring.get_password(rail_type, "arrival")
    if default_arrival is None:
        default_arrival = "동대구"
    default_date = keyring.get_password(rail_type, "date")
    if default_date is None:
        default_date = today
    default_time = keyring.get_password(rail_type, "time")
    if default_time is None:
        default_time = "120000"

    if rail_type == "SRT":
        main_station = "수서"
    else:
        main_station = "서울"

    q_info = [
        inquirer.List(
            "departure",
            message="출발역 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
            choices=[main_station, "오송", "대전", "동대구", "부산", "포항"],
            default=default_departure,
        ),
        inquirer.List(
            "arrival",
            message="도착역 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
            choices=[main_station, "오송", "대전", "동대구", "부산", "포항"],
            default=default_arrival,
        ),
        inquirer.List(
            "date",
            message="출발 날짜 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
            choices=[
                (
                    (now + timedelta(days=i)).strftime("%Y/%m/%d %a"),
                    (now + timedelta(days=i)).strftime("%Y%m%d"),
                )
                for i in range(28)
            ],
            default=default_date,
        ),
        inquirer.List(
            "time",
            message="출발 시각 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
            choices=[
                ("00", "000000"),
                ("02", "020000"),
                ("04", "040000"),
                ("06", "060000"),
                ("08", "080000"),
                ("10", "100000"),
                ("12", "120000"),
                ("14", "140000"),
                ("16", "160000"),
                ("18", "180000"),
                ("20", "200000"),
                ("22", "220000"),
            ],
            default=default_time,
        ),
    ]
    if rail_type == "KTX":
        q_info.append(
            inquirer.List(
                "passenger",
                message="승객수 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
                choices=list(range(1, 10)),
            )
        )
    info = inquirer.prompt(q_info)
    if info is None:
        return

    if info["departure"] == info["arrival"]:
        print(colored("출발역과 도착역이 같습니다", "green", "on_red") + "\n")
        return

    keyring.set_password(rail_type, "departure", info["departure"])
    keyring.set_password(rail_type, "arrival", info["arrival"])
    keyring.set_password(rail_type, "date", info["date"])
    keyring.set_password(rail_type, "time", info["time"])

    if info["date"] == today and int(info["time"]) < int(this_time):
        info["time"] = this_time

    # choose trains
    if rail_type == "SRT":
        trains = rail.search_train(
            info["departure"],
            info["arrival"],
            info["date"],
            info["time"],
            available_only=False,
        )
    else:
        trains = rail.search_train(
            info["departure"],
            info["arrival"],
            info["date"],
            info["time"],
            passengers=[AdultPassenger(info["passenger"])],
            include_no_seats=True,
        )

    if len(trains) == 0:
        print(colored("예약 가능한 열차가 없습니다", "green", "on_red") + "\n")
        return
    if rail_type == "SRT":
        seat_type = SeatType
    else:
        seat_type = ReserveOption

    q_choice = [
        inquirer.Checkbox(
            "trains",
            message="예약할 열차 선택 (↕:이동, Space: 선택, Enter: 완료, Ctrl-C: 취소)",
            choices=[(train.__repr__(), i) for i, train in enumerate(trains)],
            default=list(range(min(6, len(trains)))),
        ),
        inquirer.List(
            "type",
            message="선택 유형 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
            choices=[
                ("일반실 우선", seat_type.GENERAL_FIRST),
                ("일반실만", seat_type.GENERAL_ONLY),
                ("특실 우선", seat_type.SPECIAL_FIRST),
                ("특실만", seat_type.SPECIAL_ONLY),
            ],
        ),
    ]
    choice = inquirer.prompt(q_choice)
    if choice is None:
        return

    if len(choice["trains"]) == 0:
        print(colored("선택한 열차가 없습니다!", "green", "on_red") + "\n")
        return

    tgprintf = get_telegram()

    # start searching
    while True:
        try:
            # print(datetime.now().strftime("%H:%M:%S"))
            print(".", end="", flush=True)

            if rail_type == "SRT":
                trains = rail.search_train(
                    info["departure"],
                    info["arrival"],
                    info["date"],
                    info["time"],
                    available_only=False,
                )
            else:
                trains = rail.search_train(
                    info["departure"],
                    info["arrival"],
                    info["date"],
                    info["time"],
                    passengers=[AdultPassenger(info["passenger"])],
                    include_no_seats=True,
                )

            for i, train in enumerate(trains):
                if i in choice["trains"]:
                    # print(train)

                    # check seat availablity
                    if (
                        (
                            choice["type"]
                            in [seat_type.GENERAL_FIRST, seat_type.SPECIAL_FIRST]
                            and (
                                (rail_type == "SRT" and train.seat_available())
                                or (rail_type == "KTX" and train.has_seat())
                            )
                        )
                        or (
                            choice["type"] == seat_type.GENERAL_ONLY
                            and (
                                (rail_type == "SRT" and train.general_seat_available())
                                or (rail_type == "KTX" and train.has_general_seat())
                            )
                        )
                        or (
                            choice["type"] == seat_type.SPECIAL_ONLY
                            and (
                                (rail_type == "SRT" and train.special_seat_available())
                                or (rail_type == "KTX" and train.has_special_seat())
                            )
                        )
                    ):
                        if rail_type == "SRT":
                            reserve = rail.reserve(train, special_seat=choice["type"])
                            print(
                                colored(
                                    "\n\n\n🎊예매 성공!!!🎊\n"
                                    + reserve.__repr__()
                                    + "\n"
                                    + reserve.tickets.__repr__()
                                    + "\n\n",
                                    "red",
                                    "on_green",
                                )
                            )
                        else:
                            reserve = rail.reserve(
                                train,
                                [AdultPassenger(info["passenger"])],
                                choice["type"],
                            )
                            print(
                                colored(
                                    "\n\n\n🎊예매 성공!!!🎊\n"
                                    + reserve.__repr__()
                                    + "\n\n",
                                    "red",
                                    "on_green",
                                )
                            )
                        asyncio.run(tgprintf(reserve.__repr__()))
                        return

            time.sleep(1 + 2 * random())

        except Exception as ex:
            print(ex)

            answer = inquirer.prompt(
                [inquirer.Confirm("continue", message="계속할까요", default=True)]
            )

            if not answer["continue"]:
                return


def check_reservation(rail_type="SRT"):
    rail = login(rail_type)

    while True:
        if rail_type == "SRT":
            reservations = rail.get_reservations()
        else:
            reservations = rail.reservations()

        if len(reservations) == 0:
            print(colored("예약 내역이 없습니다", "green", "on_red") + "\n")
            return

        cancel_choices = [
            (reservation.__repr__(), i) for i, reservation in enumerate(reservations)
        ]
        cancel_choices.insert(0, ("돌아가기", -1))
        q_cancel = [
            inquirer.List(
                "cancel",
                message="예약 취소 (Enter: 결정)",
                choices=cancel_choices,
            )
        ]
        cancel = inquirer.prompt(q_cancel)

        if cancel is None or cancel["cancel"] == -1:
            return

        answer = inquirer.prompt(
            [
                inquirer.Confirm(
                    "continue",
                    message=colored("정말 취소하시겠습니까", "green", "on_red"),
                )
            ],
        )

        if answer["continue"]:
            try:
                rail.cancel(reservations[cancel["cancel"]])
            except Exception as err:
                print(err)
                return


if __name__ == "__main__":
    srtgo()
