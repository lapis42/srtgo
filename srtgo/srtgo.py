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
    # Login
    id = keyring.get_password("SRT", "id")
    password = keyring.get_password("SRT", "pass")

    if (id is None) or (password is None):
        q_login = [
            inquirer.Text(
                "id", message="SRT 계정 아이디 (멤버십 번호, 이메일, 전화번호)"
            ),
            inquirer.Text("pass", message="SRT 계정 패스워드"),
        ]
        login = inquirer.prompt(q_login)
        id = login["id"]
        password = login["pass"]

        if id and password:
            keyring.set_password("SRT", "id", id)
            keyring.set_password("SRT", "pass", password)

    srt = SRT(id, password)

    is_telegram = False
    token = keyring.get_password("telegram", "token")
    chat_id = keyring.get_password("telegram", "chat_id")
    if (token is None) or (chat_id is None):
        answer = inquirer.prompt(
            [
                inquirer.Confirm(
                    "confirm",
                    message="텔레그램 token과 chat_id가 있습니까 (https://gabrielkim.tistory.com/entry/Telegram-Bot-Token-%EB%B0%8F-Chat-Id-%EC%96%BB%EA%B8%B0 참고)",
                )
            ]
        )
        if answer["confirm"]:
            q_telegram = [
                inquirer.Text(
                    "token",
                    message="텔레그램 token (예 53515151535:SDfgEgvfefEfEf-dsfewfefdF)",
                ),
                inquirer.Text("chat_id", message="텔레그램 chat_id (예 -213125185)"),
            ]
            telegram_info = inquirer.prompt(q_telegram)
            token = telegram_info["token"]
            chat_id = telegram_info["chat_id"]
            if token and chat_id:
                keyring.set_password("telegram", "token", token)
                keyring.set_password("telegram", "chat_id", chat_id)
            is_telegram = True
    else:
        is_telegram = True

    async def tgprintf(text):
        bot = telegram.Bot(token=token)
        async with bot:
            await bot.send_message(chat_id=chat_id, text=text)

    # 출발역 / 도착역 / 날짜 / 시각 선택
    q_info = [
        inquirer.List(
            "departure",
            message="출발역 선택",
            choices=["수서", "포항", "오송", "대전", "동대구", "부산"],
            default="수서",
        ),
        inquirer.List(
            "arrival",
            message="도착역 선택",
            choices=["수서", "포항", "오송", "대전", "동대구", "부산"],
            default="포항",
        ),
        inquirer.List(
            "date",
            message="출발 날짜 선택",
            choices=[
                (datetime.now() + timedelta(days=i)).strftime("%Y%m%d")
                for i in range(3)
            ],
        ),
        inquirer.List(
            "time",
            message="출발 시각 선택",
            choices=[
                "00",
                "02",
                "04",
                "06",
                "08",
                "10",
                "12",
                "14",
                "16",
                "18",
                "20",
                "22",
            ],
        ),
    ]
    info = inquirer.prompt(q_info)

    if info["departure"] == info["arrival"]:
        print(colored("출발역과 도착역이 같습니다"), "red")
        return

    # choose trains
    trains = srt.search_train(
        info["departure"],
        info["arrival"],
        info["date"],
        info["time"] + "0000",
        available_only=False,
    )

    if len(trains) == 0:
        print(colored("예약 가능한 열차가 없습니다", "red"))
        return

    q_choice = [
        inquirer.Checkbox(
            "trains",
            message="예약할 열차 선택",
            choices=[(train.__repr__(), i) for i, train in enumerate(trains)],
            default=list(range(min(6, len(trains)))),
        ),
        inquirer.List(
            "type",
            message="선택 유형",
            choices=[
                ("일반실 우선", SeatType.GENERAL_FIRST),
                ("일반실만", SeatType.GENERAL_ONLY),
                ("특실 우선", SeatType.SPECIAL_FIRST),
                ("특실만", SeatType.SPECIAL_ONLY),
            ],
        ),
    ]
    choice = inquirer.prompt(q_choice)
    if len(choice["trains"]) == 0:
        print(colored("선택한 열차가 없습니다!", "red"))
        return

    # start searching
    while True:
        try:
            trains = srt.search_train(
                info["departure"],
                info["arrival"],
                info["date"],
                info["time"] + "0000",
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
                        print("\n예매 성공!!!\n", colored(reserve.__repr__(), "green"))
                        if is_telegram:
                            asyncio.run(tgprintf(reserve.__repr__()))
                        return

            print()
            time.sleep(2)

        except Exception as ex:
            print(ex)

            answer = inquirer.prompt(
                [inquirer.Confirm("continue", message="계속할까요", default=True)]
            )

            if ~answer["continue"]:
                return


if __name__ == "__main__":
    srtgo()
