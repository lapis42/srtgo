# SRTgo: K-Train (KTX, SRT) Reservation Macro
[![Upload Python Package](https://github.com/lapis42/srtgo/actions/workflows/python-publish.yml/badge.svg)](https://github.com/lapis42/srtgo/actions/workflows/python-publish.yml)
[![Downloads](https://static.pepy.tech/badge/srtgo)](https://pepy.tech/project/srtgo)
[![Downloads](https://static.pepy.tech/badge/srtgo/month)](https://pepy.tech/project/srtgo)
[![Python version](https://img.shields.io/pypi/pyversions/srtgo)](https://pypistats.org/packages/srtgo)

> [!WARNING]
> 본 프로그램의 모든 상업적, 영리적 이용을 엄격히 금지합니다. 본 프로그램 사용에 따른 민형사상 책임을 포함한 모든 책임은 사용자에게 따르며, 본 프로그램의 개발자는 민형사상 책임을 포함한 어떠한 책임도 부담하지 아니합니다. 📥본 프로그램을 내려받음으로써 모든 사용자는 위 사항에 아무런 이의 없이 동의하는 것으로 간주됩니다.

> [!IMPORTANT]
> 본 프로그램에 입력하는 아이디, 비번, 카드번호, 예매 설정 등은 로컬 컴퓨터에 [keyring 모듈](https://pypi.org/project/keyring/)을 통하여 저장하며 그 이외의 위치에 네트워크 전송 등을 통하여 공유되지 않습니다.

- 본 프로그램은 SRT 및 KTX 기차표 예매를 자동화하는 매크로입니다.
- 예약이 완료되면 텔레그램 알림을 전송합니다.
  - [Bot Token 및 Chat Id 얻기](https://gabrielkim.tistory.com/entry/Telegram-Bot-Token-%EB%B0%8F-Chat-Id-%EC%96%BB%EA%B8%B0).
- 신용카드 정보를 입력해두면, 예매 직후에 결제되도록 할 수 있습니다.
- 자주 사용하는 역을 지정할 수 있습니다.
- 어린이 혹은 우대 예매 설정을 할 수 있습니다.

---
> [!WARNING]
> All commercial and commercial use of this program is strictly prohibited. Use of this program is at your own risk, and the developers of this program shall not be liable for any liability, including civil or criminal liability. 📥By downloading this program, all users agree to the above without any objection.

> [!IMPORTANT]
> Through the keyring module, the information such as username, password, credit card, departure station, and arrival station is stored on the local computer.
> The ID, password, card number, reservation settings, etc. entered in this program are stored on the local computer through the [keyring module](https://pypi.org/project/keyring/) and are not shared through network transmission to any other location.

- This program is a macro that automates the reservation of SRT and KTX train tickets.
- After the reservation is completed, a Telegram notification will be sent.
- Tickets can be confirmed or canceled.
- You can enter your credit card information to be charged immediately after you make your reservation.
- You can specify your favorite stations.
- You can set up child or accessible ticketing.

## Installation / Update
