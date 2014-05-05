#!/usr/bin/env python
# vim: fileencoding=utf-8: expandtab: softtabstop=4: shiftwidth=4: foldmethod=marker: fmr=#{,#}

"""
TrollBox v0.2

btc-e.com chat channal
"""

from   __future__     import print_function
from   sys            import argv, exit
from   getopt         import getopt
from   re             import sub as re_sub, compile as re_compile
from   htmlentitydefs import name2codepoint
from   time           import sleep
import websocket
from   requests       import get as httpget
from   json           import loads as jsload
from   bytebuffer     import ByteBuffer

__author__ = "slavamnemonic@gmail.com"

COLOR_0   = "\033[m"      # серый
COLOR_1   = "\033[1m"     # жирный (bold)
COLOR_2   = "\033[0;32m"  # зелёный
COLOR_3   = "\033[1;32m"  # ярко-зелёный
COLOR_4   = "\033[0;33m"  # жёлтый
COLOR_5   = "\033[1;33m"  # ярко-жёлтый
COLOR_6   = "\033[0;36m"  # бирюзовый
COLOR_7   = "\033[1;36m"  # ярко-бирюзовый
COLOR_8   = "\033[1;31m"  # ярко-красный
COLOR_9   = "\033[1;34m"  # серый
COLOR_10  = "\033[1;30m"  # ярко-синий

COLORS   = (COLOR_2, COLOR_3, COLOR_4, COLOR_5,
            COLOR_6, COLOR_7, COLOR_8, COLOR_9)

CHANNEL  = "chat_en"
BTCE_CHAT_URL = "wss://ws.pusherapp.com/app/4e0ebd7a8b66fa3554a4?protocol=6&client=js&version=2.0.0&flash=false"
TRADINGVIEW_CHAT = "https://www.tradingview.com/message-pipe-es/public"
CONNECTION_TIMEOUT = 120
XHR_READ_SIZE = 5
RE_USERNAMES = re_compile("(^\w*,)|(^@\w*)")


def btce_transport(url=BTCE_CHAT_URL):##{
    while True:
        try:
            ws = websocket.WebSocket()
            ws.connect(url)
            ws.settimeout(CONNECTION_TIMEOUT)
        except Exception, e:
            print("[!!!] Esteblish connection error: ", e)
            sleep(3)

        chat_handshake(ws)
        yield ws
##}

def tradingview_transport(url=TRADINGVIEW_CHAT):##{
    while True:
        print("\nConnecting to tradingview...")
        try:
            tmp = httpget(url, stream=True, timeout=CONNECTION_TIMEOUT)
            print("Connected")
            yield tmp
        except Exception, e:
            print("[!!!] Esteblish connection error: ", e)
            sleep(3)
##}

def chat_handshake(ws):##{
    hello_msg = """{"event":"pusher:subscribe","data":{"channel":"%s"}}"""% CHANNEL
    ws.recv()
    ws.send(hello_msg)
    subscribe_status = ws.recv()

    return jsload(subscribe_status)
##}

def deserialize(json):##{
    obj_lvl1 = jsload(json)
    tmp = jsload(jsload(obj_lvl1.get("data", "{}")))
    if not isinstance(tmp, dict):
        tmp = {}

    return tmp
##}

def string( val ):  #{
    """
    Returns either a <str> or a <unicode>

    >>> print repr( string( 123 ) )
    '123'
    >>> print repr( string( None ) )
    'None'
    """
    if not isinstance( val, basestring ):
        try:    val = str( val )
        except: val = unicode( val )

    return val
#}

def replace_entities( text ):  #{
    """ Replaces HTML/XML character references and entities in a text string with
        actual Unicode characters.

        @param text The HTML (or XML) source text.
        @return The plain text, as a Unicode string, if necessary.

        >>> a = '&lt;a href=&quot;/abc?a=50&amp;amp;b=test&quot;&gt;'
        >>> print replace_entities( a )
        <a href="/abc?a=50&amp;b=test">
    """
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re_sub("&#?\w+;", fixup, string(text))
#}

def message_preprocess(msg, logins=set()):##{
    """Colorize user name in mesAsage

    msg    - message string
    logins - set of usernames

    Answer message username set at start of string with comma
    Color user name if we have this name at logins set of users
    """

    parts = [st for st in RE_USERNAMES.split(msg) if st]
    if len(parts) == 1: return msg

    head, tail = parts[0], parts[1]
    if not head in logins: return msg

    user_color = COLORS[hash(head) % len(COLORS)]
    return "{}{}{},{}".format(user_color, head, COLOR_0, tail)
##}

def btcex(transport):##{
    """Consume chat messages

    ws - BTC-E ready WebSocket

    returns tuple of user name and chat message
    """

    ws = next(transport)
    while True:
        try:
            chat_message = ws.recv()
        except websocket.socket.sslerror:
            ws = next(transport)
            continue

        struct = deserialize(chat_message)
        login  = struct.get("login")
        msg    = struct.get("msg",   "").encode("utf-8", errors="replace")

        yield(login, msg)
##}

def tradingviewx(transport):##{
    buffer = ByteBuffer()
    xhr = next(transport)

    while True:
        try:
            data = xhr.raw.read(XHR_READ_SIZE)
        except Exception:
            xhr = next(transport)
            continue

        buffer.write(data)
        line = buffer.read_until(b"\r\n", consume=True)

        if not line: continue
        if line == ": -1": continue
        if line.startswith("data: "): line = line[6:]

        try:
            pkg = jsload(line)
        except Exception:
            continue

        channel = pkg.get("text", {}).get("channel")
        if channel != "chat_bitcoin": continue

        content = pkg.get("text").get("content")
        login = content.get('username')
        msg = content.get("text", "").encode("utf-8", errors="replace")
        meta = content.get("meta", {})
        url = meta.get("url", "").encode("utf-8", errors="replace")
        if url:
            msg = "{}\n{:<19}{}{}{}".format(msg, "", COLOR_10, url, COLOR_0)
        if not msg: continue

        yield(login, msg)
##}

def chat_loop(chat_stream):##{
    logins = set()
    for login, msg in chat_stream:
        if not login: continue
        logins.add(login)

        format_params = {
            "login"     : login,
            "msg"       : message_preprocess(msg, logins),
            "login_clr" : COLORS[hash(login) % len(COLORS)],
            "colon_clr" : COLOR_10,
            "nocollor"  : COLOR_0
        }

        print("{login_clr}{login:13}{colon_clr}: {nocollor} {msg} ".format(**format_params))
##}

def help():##{
    print("""
btce-trollbox.py <option>

    --help:         You are here
    --bte:          BTC-E Troll Box
    --tradingview:  Tradingview small talk
""")
##}

def main():##{
    stream = None
    opts, args = getopt(argv[1:], "-h", longopts=("help", "btce", "tradingview"))

    for opt, value in opts:
        if opt in ("-h", "--help"):
            help()
            exit(0)

        if opt == "--btce":
            stream = btcex(btce_transport())
            continue

        if opt == "--tradingview":
            stream = tradingviewx(tradingview_transport())
            continue

        if opt == "chat_en":
            CHANNEL = "chat_en"

        if opt == "chat_ru":
            CHANNEL = "chat_ru"
            
        if opt == "chat_cn":
            CHANNEL = "chat_cn"

    if not stream:
        stream = btcex(btce_transport())
    
    chat_loop(stream)
##}

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

    print("\nExit")
