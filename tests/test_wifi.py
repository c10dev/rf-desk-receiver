from deskrx.wifi import parse_netsh, parse_nmcli

EN = """\
Interface name : Wi-Fi 
There are 3 networks currently visible. 

SSID 1 : School-AP
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : 10:00:00:00:00:01
         Signal             : 80%
         Radio type         : 802.11ac
         Channel            : 36
    BSSID 2                 : 10:00:00:00:00:02
         Signal             : 40%
         Radio type         : 802.11n

SSID 2 : 
    Network type            : Infrastructure
    BSSID 1                 : aa:bb:cc:dd:ee:ff
         Signal             : 60%
"""

KO = """\
인터페이스 이름 : Wi-Fi
현재 2개의 네트워크가 표시되어 있습니다.

SSID 1 : 학교와이파이
    네트워크 유형           : 인프라
    인증                    : WPA2-개인
    BSSID 1                 : 10:00:00:00:00:01
         신호               : 80%
         무선 종류          : 802.11ac
         채널               : 36
SSID 2 : My iPhone
    BSSID 1                 : 22:22:22:22:22:22
         신호               : 100%
"""


def test_netsh_english_two_bssids_and_hidden():
    obs = parse_netsh(EN, 5.0)
    assert [(o.address, o.name, o.rssi) for o in obs] == [
        ("10:00:00:00:00:01", "School-AP", -60),
        ("10:00:00:00:00:02", "School-AP", -80),
        ("AA:BB:CC:DD:EE:FF", None, -70),
    ]
    assert all(o.source == "WIFI" and o.t == 5.0 for o in obs)


def test_netsh_korean_output():
    obs = parse_netsh(KO, 1.0)
    assert [(o.address, o.name, o.rssi) for o in obs] == [
        ("10:00:00:00:00:01", "학교와이파이", -60),
        ("22:22:22:22:22:22", "My iPhone", -50),
    ]
    assert obs[1].hint == "HOTSPOT"


def test_netsh_crlf_and_empty():
    assert len(parse_netsh(EN.replace("\n", "\r\n"), 0)) == 3
    assert parse_netsh("", 0) == []


NMCLI = (
    "10\\:00\\:00\\:00\\:00\\:01:School-AP:80\n"
    "AA\\:BB\\:CC\\:DD\\:EE\\:FF::60\n"
    "AA\\:BB\\:CC\\:DD\\:EE\\:11:--:40\n"
    "20\\:00\\:00\\:00\\:00\\:01:Cafe\\: Free:100\n"
    "garbage line\n"
)


def test_nmcli_escaped_bssid_hidden_ssid():
    obs = parse_nmcli(NMCLI, 9.0)
    assert [(o.address, o.name, o.rssi) for o in obs] == [
        ("10:00:00:00:00:01", "School-AP", -60),
        ("AA:BB:CC:DD:EE:FF", None, -70),
        ("AA:BB:CC:DD:EE:11", None, -80),
        ("20:00:00:00:00:01", "Cafe: Free", -50),
    ]
