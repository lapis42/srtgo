# %pip install SRTrain
# %pip install prompt-toolkit -U
# %pip install inquirer
# %pip install python-telegram-bot --upgrade --pre
# %pip install termcolor

import click
import inquirer
import keyring
import time
import telegram
import asyncio
from termcolor import colored
from datetime import datetime, timedelta
from SRT import SRT
from SRT.seat_type import SeatType


@click.command()
def srtgo():
    while True:
        menu = [
            inquirer.List(
                "menu",
                message="메뉴 선택 (↕:이동, Enter: 완료)",
                choices=[
                    ("예약 시작", 1),
                    ("로그인 설정", 2),
                    ("텔레그램 설정", 3),
                    ("나가기", 4),
                ],
            )
        ]
        choice = inquirer.prompt(menu)

        if choice is None:
            return

        if choice["menu"] == 1:
            reserve()
        elif choice["menu"] == 2:
            set_login()
        elif choice["menu"] == 3:
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
        asyncio.run(tgprintf("[SRT] 텔레그램 설정 완료"))
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


def set_login():
    if keyring.get_password("SRT", "ok") is not None:
        id = keyring.get_password("SRT", "id")
        password = keyring.get_password("SRT", "pass")
    else:
        id = ""
        password = ""

    q_login = [
        inquirer.Text(
            "id", message="SRT 계정 아이디 (멤버십 번호, 이메일, 전화번호)", default=id
        ),
        inquirer.Text("pass", message="SRT 계정 패스워드", default=password),
    ]
    login = inquirer.prompt(q_login)

    if login is None:
        return False

    id = login["id"]
    password = login["pass"]

    if id and password:
        keyring.set_password("SRT", "id", id)
        keyring.set_password("SRT", "pass", password)
    else:
        return False

    try:
        SRT(id, password)
        keyring.set_password("SRT", "ok", "1")
        return True
    except Exception as err:
        print(err)
        keyring.delete_password("SRT", "ok")
        return False


def login():
    # login
    if keyring.get_password("SRT", "ok") is None:
        set_login()

    id = keyring.get_password("SRT", "id")
    password = keyring.get_password("SRT", "pass")
    return SRT(id, password)


def reserve():
    srt = login()

    # 출발역 / 도착역 / 날짜 / 시각 선택
    default_departure = keyring.get_password("SRT", "departure")
    if default_departure is None:
        default_departure = "수서"
    default_arrival = keyring.get_password("SRT", "arrival")
    if default_arrival is None:
        default_arrival = "동대구"
    default_date = keyring.get_password("SRT", "date")
    if default_date is None:
        default_date = "20230101"
    default_time = keyring.get_password("SRT", "time")
    if default_time is None:
        default_time = "120000"

    q_info = [
        inquirer.List(
            "departure",
            message="출발역 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
            choices=["수서", "오송", "대전", "동대구", "부산", "포항"],
            default=default_departure,
        ),
        inquirer.List(
            "arrival",
            message="도착역 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
            choices=["수서", "오송", "대전", "동대구", "부산", "포항"],
            default=default_arrival,
        ),
        inquirer.List(
            "date",
            message="출발 날짜 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소)",
            choices=[
                (
                    (datetime.now() + timedelta(days=i)).strftime("%Y/%m/%d %a"),
                    (datetime.now() + timedelta(days=i)).strftime("%Y%m%d"),
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
    info = inquirer.prompt(q_info)
    if info is None:
        return

    if info["departure"] == info["arrival"]:
        print(colored("출발역과 도착역이 같습니다"), "red")
        return

    keyring.set_password("SRT", "departure", info["departure"])
    keyring.set_password("SRT", "arrival", info["arrival"])
    keyring.set_password("SRT", "date", info["date"])
    keyring.set_password("SRT", "time", info["time"])

    # choose trains
    trains = srt.search_train(
        info["departure"],
        info["arrival"],
        info["date"],
        info["time"],
        available_only=False,
    )

    if len(trains) == 0:
        print(colored("예약 가능한 열차가 없습니다", "red"))
        return

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
                ("일반실 우선", SeatType.GENERAL_FIRST),
                ("일반실만", SeatType.GENERAL_ONLY),
                ("특실 우선", SeatType.SPECIAL_FIRST),
                ("특실만", SeatType.SPECIAL_ONLY),
            ],
        ),
    ]
    choice = inquirer.prompt(q_choice)
    if choice is None:
        return

    if len(choice["trains"]) == 0:
        print(colored("선택한 열차가 없습니다!", "red"))
        return

    tgprintf = get_telegram()

    # start searching
    while True:
        try:
            trains = srt.search_train(
                info["departure"],
                info["arrival"],
                info["date"],
                info["time"],
                available_only=False,
            )

            for i, train in enumerate(trains):
                if i in choice["trains"]:
                    print(train)

                    # check seat availablity
                    if (
                        (
                            choice["type"]
                            in [SeatType.GENERAL_FIRST, SeatType.SPECIAL_FIRST]
                            and train.seat_available()
                        )
                        or (
                            choice["type"] == SeatType.GENERAL_ONLY
                            and train.general_seat_available()
                        )
                        or (
                            choice["type"] == SeatType.SPECIAL_ONLY
                            and train.special_seat_available()
                        )
                    ):
                        reserve = srt.reserve(train, special_seat=choice["type"])
                        print(
                            colored(
                                "\n\n🎊예매 성공!!!🎊\n" + reserve.__repr__() + "\n\n",
                                "green",
                            )
                        )
                        asyncio.run(tgprintf(reserve.__repr__()))
                        return

            print()
            time.sleep(2)

        except Exception as ex:
            print(ex)

            answer = inquirer.prompt(
                [inquirer.Confirm("continue", message="계속할까요", default=True)]
            )

            if not answer["continue"]:
                return


if __name__ == "__main__":
    srtgo()
