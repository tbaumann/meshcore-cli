#!/usr/bin/python
""" 
    mccli.py : CLI interface to MeschCore BLE companion app
"""
import asyncio
import os
import sys
import getopt
import json
import datetime
import time
import shlex
import logging
from pathlib import Path

from meshcore import TCPConnection
from meshcore import BLEConnection
from meshcore import SerialConnection
from meshcore import MeshCore
from meshcore import EventType
from meshcore import logger

#logger.setLevel(logging.DEBUG)

# default address is stored in a config file
MCCLI_CONFIG_DIR = str(Path.home()) + "/.config/meshcore/"
MCCLI_ADDRESS = MCCLI_CONFIG_DIR + "default_address"

# Fallback address if config file not found
# if None or "" then a scan is performed
ADDRESS = ""
JSON = False

PS = None
CS = None

# Subscribe to incoming messages
async def handle_message(event):
    await process_event_message(MC, event, False)

async def subscribe_to_msgs(mc):
    global PS, CS
    # Subscribe to private messages
    if PS is None :
        PS = mc.subscribe(EventType.CONTACT_MSG_RECV, handle_message)
    # Subscribe to channel messages
    if CS is None :
        CS = mc.subscribe(EventType.CHANNEL_MSG_RECV, handle_message)
    await mc.start_auto_message_fetching()

async def interactive_loop(mc) :
    print("Interactive mode, use \"to\" to selects contact, \"lc\" to list contacts, \"$\" to issue a command.\n You can send messages using the \"send\" command, a quote, or write your message after the prompt.\n \"quit\" or \"q\" will end interactive mode")

    await mc.ensure_contacts()
    contact = next(iter(mc.contacts.items()))[1]

    try:
        while True:
            print(f"{contact['adv_name']}> ", end="", flush=True)
            line = (await asyncio.to_thread(sys.stdin.readline)).rstrip('\n')

            if line == "" : # blank line
                pass

            elif line.startswith("$") : # command
                args = shlex.split(line[1:])
                await process_cmds(mc, args)

            elif line.startswith(".") or\
                    line.startswith("set ") or\
                    line.startswith("get ") or\
                    line.startswith("public") or\
                    line.startswith("clock") or\
                    line.startswith("time") or\
                    line.startswith("ver") or\
                    line.startswith("reboot") or\
                    line.startswith("advert") or\
                    line.startswith("chan") or\
                    line.startswith("card") : # terminal chat commands
                args = shlex.split(line)
                await process_cmds(mc, args)

            elif line.startswith("to ") : # dest
                dest = line[3:]
                nc = mc.get_contact_by_name(dest)
                if nc is None:
                    print(f"Contact '{dest}' not found in contacts.")
                    return
                else :
                    contact = nc

            elif line == "to" :
                print(contact["adv_name"])

            elif line == "reset path" : # reset path from terminal chat
                res = await mc.commands.reset_path(contact)
                logger.debug(res)
                if res.type == EventType.ERROR:
                    print(f"Error resetting path: {res}")
                else:
                    print(f"Path to contact['adv_name'] has been reset")
                await mc.commands.get_contacts()

            elif line == "quit" or line == "q" :
                break

            elif line == "list" : # list command from chat displays contacts on a line
                it = iter(mc.contacts.items())
                c = next(it)
                print (c[1]["adv_name"], end="")
                for c in it :
                    print(f", {c[1]['adv_name']}", end="")
                print("")
                
            else :
                if line.startswith("send") :
                    line = line[5:]
                if line.startswith("\"") :
                    line = line[1:]
                result = await mc.commands.send_msg(contact, line)
                if result.type == EventType.ERROR:
                    print(f"⚠️ Failed to send message: {result.payload}")
                    continue
                    
                exp_ack = result.payload["expected_ack"].hex()
                res = await mc.wait_for_event(EventType.ACK, attribute_filters={"code": exp_ack}, timeout=5)
                if res is None :
                    print ("#", end="")
                else :
                    print ("~", end="")

    except KeyboardInterrupt:
        mc.stop()
        print("Exiting cli")
    except asyncio.CancelledError:
        # Handle task cancellation from KeyboardInterrupt in asyncio.run()
        print("Exiting cli")

async def process_event_message(mc, ev, json_output, end="\n"):
    if ev.type == EventType.NO_MORE_MSGS:
        logger.debug("No more messages")
        return False
    elif ev.type == EventType.ERROR:
        logger.error(f"Error retrieving messages: {ev.payload}")
        return False
    elif json_output :
        print(json.dumps(ev.payload, indent=4), end=end, flush=True)
    else :
        await mc.ensure_contacts()
        data = ev.payload
        if (data['type'] == "PRIV") :
            ct = mc.get_contact_by_key_prefix(data['pubkey_prefix'])
            if ct is None:
                logger.info(f"Unknown contact with pubkey prefix: {data['pubkey_prefix']}")
                name = data["pubkey_prefix"]
            else:
                name = ct["adv_name"]
            if data['path_len'] == 255 :
                path_str = "D"
            else :
                path_str = str(data['path_len'])
            print(f"{name}({path_str}): {data['text']}")
        elif (data['type'] == "CHAN") :
            if data['path_len'] == 255 :
                path_str = "D"
            else :
                path_str = str(data['path_len'])
            print(f"ch{data['channel_idx']}({path_str}): {data['text']}")
        else:
            print(json.dumps(ev.payload))
    return True

async def next_cmd(mc, cmds, json_output=False):
    """ process next command """
    argnum = 0
    if cmds[0].startswith(".") : # override json_output
        json_output = True
        cmd = cmds[0][1:]
    else:
        cmd = cmds[0]
    match cmd :
        case "ver" | "v" :
            res = await mc.commands.send_device_query()
            logger.debug(res)
            if res.type == EventType.ERROR :
                print(f"ERROR: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else :
                print("Devince info :")
                if res.payload["fw ver"] >= 3:
                    print(f" Model: {res.payload['model']}")
                    print(f" Version: {res.payload['ver']}")
                    print(f" Build date: {res.payload['fw_build']}")
                else :
                    print(f" Firmware version : {res.payload['fw ver']}")

        case "clock" :
            if len(cmds) > 1 and cmds[1] == "sync" :
                argnum=1
                res = await mc.commands.set_time(int(time.time()))
                logger.debug(res)
                if res.type == EventType.ERROR:
                    print(f"Error setting time: {res}")
                elif json_output :
                    print(json.dumps(res.payload, indent=4))
                else :
                    print("Time synced")
            else:
                res = await mc.commands.get_time()
                timestamp = res.payload["time"]
                if res.type == EventType.ERROR:
                    print(f"Error getting time: {res}")
                elif json_output :
                    print(json.dumps(res.payload, indent=4))
                else :
                    print('Current time :'
                        f' {datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")}'
                        f' ({timestamp})')

        case "sync_time"|"clock sync"|"st": # keep if for the st shortcut
            res = await mc.commands.set_time(int(time.time()))
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error syncing time: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Time synced")

        case "time" :
            argnum = 1
            res = await mc.commands.set_time(cmds[1])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print (f"Error setting time: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Time set")

        case "set":
            argnum = 2
            match cmds[1]:
                case "help" :
                    argnum = 1
                    print("""Available parameters :
 pin <pin>               : ble pin
 radio <freq,bw,sf,cr>   : radio params 
 tuning <rx_dly,af>      : tuning params
 tx <dbm>                : tx power
 name <name>             : node name
 lat <lat>               : latitude
 lon <lon>               : longitude
 coords <lat,lon>        : coordinates""")
                case "pin":
                    res = await mc.commands.set_devicepin(cmds[2])
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error: {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print("ok")
                case "radio":
                    params=cmds[2].split(",")
                    res=await mc.commands.set_radio(params[0], params[1], params[2], params[3])
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error: {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print("ok")
                case "name":
                    res = await mc.commands.set_name(cmds[2])
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error: {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print("ok")
                case "tx":
                    res = await mc.commands.set_tx_power(cmds[2])
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error: {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print("ok")
                case "lat":
                    res = await mc.commands.set_coords(\
                            float(cmds[2]),\
                            mc.self_infos['adv_lon'])
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error: {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print("ok")
                case "lon":
                    res = await mc.commands.set_coords(\
                            mc.self_infos['adv_lat'],\
                            float(cmds[2]))
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error: {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print("ok")
                case "coords":
                    params=cmds[2].commands.split(",")
                    res = await mc.commands.set_coords(\
                            float(params[0]),\
                            float(params[1]))
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error: {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print("ok")
                case "tuning":
                    params=cmds[2].commands.split(",")
                    res = await mc.commands.set_tuning(
                        int(params[0]), int(params[1]))
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error: {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print("ok")

        case "get" :
            argnum = 1
            match cmds[1]:
                case "help":
                    print("""Gets parameters from node
 name : node name
 bat : battery level in mV
 coords : adv coordinates
 radio : radio parameters
 tx : tx power""")
                case "name":
                    if json_output :
                        print(json.dumps(mc.self_info["name"]))
                    else:
                        print(mc.self_info["name"])
                case "tx":
                    if json_output :
                        print(json.dumps(mc.self_info["tx_power"]))
                    else:
                        print(mc.self_info["tx_power"])
                case "coords":
                    if json_output :
                        print(json.dumps({"lat": mc.self_info["adv_lat"], "lon":mc.self_info["adv_lon"]}))
                    else:
                        print(print(f"{mc.self_info['adv_lat']},{mc.self_info['adv_lon']}"))
                case "radio":
                    if json_output :
                        print(json.dumps(
                           {"radio_freq": mc.self_info["radio_freq"],
                            "radio_sf":   mc.self_info["radio_sf"],
                            "radio_bw":   mc.self_info["radio_bw"],
                            "radio_cr":   mc.self_info["radio_cr"]}))
                    else:
                        print(f"{mc.self_info['radio_freq']},{mc.self_info['radio_sf']},{mc.self_info['radio_bw']},{mc.self_info['radio_cr']}")
                case "bat" :
                    res = await mc.commands.get_bat()
                    logger.debug(res)
                    if res.type == EventType.ERROR:
                        print(f"Error getting bat {res}")
                    elif json_output :
                        print(json.dumps(res.payload, indent=4))
                    else:
                        print(f"Battery level : {res.payload.level}")

        case "reboot" :
            res = await mc.commands.reboot()
            logger.debug(res)
            if json_output :
                print(json.dumps(res.payload, indent=4))

        case "msg" | "m" | "{" : # sends to a contact from name
            argnum = 2
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.send_msg(contact, cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending message: {res}")
            elif json_output :
                res.payload["expected_ack"] = res.payload["expected_ack"].hex()
                print(json.dumps(res.payload, indent=4))

        case "chan"|"ch" :
            argnum = 2
            res = await mc.commands.send_chan_msg(int(cmds[1]), cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending message: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "public" | "dch" : # default chan
            argnum = 1
            res = await mc.commands.send_chan_msg(0, cmds[1])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending message: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "cmd" | "c" | "[" :
            argnum = 2
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.send_cmd(contact, cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending cmd: {res}")
            elif json_output :
                res.payload["expected_ack"] = res.payload["expected_ack"].hex()
                print(json.dumps(res.payload, indent=4))

        case "login" | "l" | "[[" :
            argnum = 2
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.send_login(contact, cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error while loging: {res}")
            elif json_output :
                res.payload["expected_ack"] = res.payload["expected_ack"].hex()
                print(json.dumps(res.payload, indent=4))

        case "logout" :
            argnum = 1
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.send_logout(contact)
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error while logout: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "req_status" | "rs" :
            argnum = 1
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.send_statusreq(contact)
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error while requesting status: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "contacts" | "list" | "lc":
            res = await mc.commands.get_contacts()
            logger.debug(json.dumps(res.payload,indent=4))
            if res.type == EventType.ERROR:
                print(f"Error asking for contacts: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else :
                for c in res.payload.items():
                    print(c[1]["adv_name"])

        case "change_path" | "cp":
            argnum = 2 
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.change_contact_path(contact, cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error setting path: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            await mc.commands.get_contacts()

        case "reset_path" | "rp" :
            argnum = 1
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.reset_path(contact)
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error resetting path: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            await mc.commands.get_contacts()

        case "share_contact" | "sc":
            argnum = 1
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.share_contact(contact)
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error while sharing contact: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "export_contact"|"ec":
            argnum = 1
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.export_contact(contact)
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error exporting contact: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else :
                print(res.payload)

        case "card" :
            res = await mc.commands.export_contact()
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error exporting contact: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else :
                print(res.payload)

        case "remove_contact" :
            argnum = 1
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.remove_contact(contact)
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error removing contact: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "recv" | "r" :
            res = await mc.commands.get_msg()
            logger.debug(res)
            await process_event_message(mc, res, json_output)

        case "sync_msgs" | "sm":
            ret = True
            first = True
            if json_output :
                print("[", end="", flush=True)
                end=""
            else:
                end="\n"
            while ret:
                res = await mc.commands.get_msg()
                logger.debug(res)
                if res.type != EventType.NO_MORE_MSGS:
                    if not first and json_output :
                        print(",")
                ret = await process_event_message(mc, res, json_output,end=end)
                first = False
            if json_output :
                print("]")

        case "infos" | "i" :
            print(json.dumps(mc.self_info,indent=4))

        case "advert" | "a":
            res = await mc.commands.send_advert()
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending advert: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Advert sent")

        case "flood_advert":
            res = await mc.commands.send_advert(flood=True)
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending advert: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Advert sent")

        case "sleep" | "s" :
            argnum = 1
            await asyncio.sleep(int(cmds[1]))

        case "wait_msg" | "wm" :
            ev = await mc.wait_for_event(EventType.MESSAGES_WAITING)
            if ev is None:
                print("Timeout waiting msg")
            else:
                res = await mc.commands.get_msg()
                logger.debug(res)
                await process_event_message(mc, res, json_output)

        case "trywait_msg" | "wmt" :
            argnum = 1
            if await mc.wait_for_event(EventType.MESSAGES_WAITING, timeout=int(cmds[1])) :
                res = await mc.commands.get_msg()
                logger.debug(res)
                await process_event_message(mc, res, json_output)

        case "wmt8"|"]":
            if await mc.wait_for_event(EventType.MESSAGES_WAITING, timeout=8) :
                res = await mc.commands.get_msg()
                logger.debug(res)
                await process_event_message(mc, res, json_output)

        case "wait_ack" | "wa" | "}":
            res = await mc.wait_for_event(EventType.ACK, timeout = 5)
            logger.debug(res)
            if res is None:
                print("Timeout waiting ack")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "wait_login" | "wl" | "]]":
            res = await mc.wait_for_event(EventType.LOGIN_SUCCESS)
            logger.debug(res)
            if res is None:
                print("Login failed : Timeout waiting response")
            elif json_output :
                if res.type == EventType.LOGIN_SUCCESS:
                    print(json.dumps({"login_success" : True}, indent=4))
                else:
                    print(json.dumps({"login_success" : False}, indent=4))
            else:
                if res.type == EventType.LOGIN_SUCCESS:
                    print("Login success")
                else:
                    print("Login failed")

        case "wait_status" | "ws" :
            res = await mc.wait_for_event(EventType.STATUS_RESPONSE)
            logger.debug(res)
            if res is None:
                print("Timeout waiting status")
            else :
                print(json.dumps(res.payload, indent=4))

        case "msgs_subscribe" | "ms" :
            await subscribe_to_msgs(mc)

        case "interactive" | "im" | "chat" :
            await subscribe_to_msgs(mc)
            await interactive_loop(mc)

        case "cli" | "@" :
            argnum = 1
            res = await mc.commands.send_cli(cmds[1])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending cli cmd: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print(f"{res.payload['response']}")

        case _ :
            if cmd[0] == "@" :
                res = await mc.commands.send_cli(cmd[1:])
                logger.debug(res)
                if res.type == EventType.ERROR:
                    print(f"Error sending cli cmd: {res}")
                elif json_output :
                    print(json.dumps(res.payload, indent=4))
                else:
                    print(f"{res.payload['response']}")

            else :
                logger.error(f"Unknown command : {cmd}")
            
    logger.debug(f"cmd {cmds[0:argnum+1]} processed ...")
    return cmds[argnum+1:]

async def process_cmds (mc, args, json_output=False) :
    cmds = args
    first = True
    if json_output :
        print("[")
    while len(cmds) > 0 :
        if not first and json_output :
            print(",")
        cmds = await next_cmd(MC, cmds, json_output)
        first = False
    if json_output :
        print("]")

def usage () :
    """ Prints some help """
    print("""meshcore-cli : CLI interface to MeschCore BLE companion app

   Usage : meshcore-cli <args> <commands>

 Arguments :
    -h : prints this help
    -j : json output
    -a <address>    : specifies device address (can be a name)
    -d <name>       : filter meshcore devices with name or address
    -t <hostname>   : connects via tcp/ip
    -p <port>       : specifies tcp port (default 5000)
    -s <port>       : use serial port <port>
    -b <baudrate>   : specify baudrate

 Available Commands and shorcuts (can be chained) :
    infos                  : print informations about the node      i 
    reboot                 : reboots node                             
    send <key> <msg>       : sends msg to node using pubkey[0:6]
    sendto <name> <msg>    : sends msg to node with given name        
    msg <name> <msg>       : same as sendto                         m 
    wait_ack               : wait an ack for last sent msg          wa
    recv                   : reads next msg                         r 
    sync_msgs              : gets all unread msgs from the node     sm
    wait_msg               : wait for a message and read it         wm
    advert                 : sends advert                           a 
    contacts               : gets contact list                      lc
    share_contact <ct>     : share a contact with others            sc
    remove_contact <ct>    : removes a contact from this node         
    reset_path <ct>        : resets path to a contact to flood      rp
    change_path <ct> <path>: change the path to a contact           cp
    get_time               : gets current time                        
    set_time <epoch>       : sets time to given epoch                 
    sync_time              : sync time with system                    
    set_name <name>        : sets node name                           
    get_bat                : gets battery level                     b 
    login <name> <pwd>     : log into a node (rep) with given pwd   l 
    wait_login             : wait for login (timeouts after 5sec)   wl
    cmd <name> <cmd>       : sends a command to a repeater (no ack) c 
    req_status <name>      : requests status from a node            rs
    wait_status            : wait and print reply                   ws
    sleep <secs>           : sleeps for a given amount of secs      s""") 
                        
async def main(argv):   
    """ Do the job """  
    global MC
    json_output = JSON
    debug = False
    address = ADDRESS
    port = 5000
    hostname = None
    serial_port = None
    baudrate = 115200
    # If there is an address in config file, use it by default
    # unless an arg is explicitely given
    if os.path.exists(MCCLI_ADDRESS) :
        with open(MCCLI_ADDRESS, encoding="utf-8") as f :
            address = f.readline().strip()

    opts, args = getopt.getopt(argv, "a:d:s:ht:p:b:jD")
    for opt, arg in opts :
        match opt:
            case "-d" : # name specified on cmdline
                address = arg
            case "-a" : # address specified on cmdline
                address = arg
            case "-s" : # serial port
                serial_port = arg
            case "-b" :
                baudrate = int(arg)
            case "-t" : 
                hostname = arg
            case "-p" :
                port = int(arg)
            case "-j" :
                json_output=True
            case "-D" :
                debug=True

    if len(args) == 0 : # no args, no action
        usage()
        return

    if (debug==True):
        logger.setLevel(logging.DEBUG)
    elif (json_output) :
        logger.setLevel(logging.ERROR)

    con = None
    if not hostname is None : # connect via tcp
        con = TCPConnection(hostname, port)
        await con.connect() 
    elif not serial_port is None : # connect via serial port
        con = SerialConnection(serial_port, baudrate)
        await con.connect()
        await asyncio.sleep(0.1)
    else : #connect via ble
        con = BLEConnection(address)
        address = await con.connect()
        if address is None or address == "" : # no device, no action
            logger.error("No device found, exiting ...")
            return

        # Store device address in configuration
        if os.path.isdir(MCCLI_CONFIG_DIR) :
            with open(MCCLI_ADDRESS, "w", encoding="utf-8") as f :
                f.write(address)

    MC = MeshCore(con, debug=debug)
    await MC.connect()

    if (json_output) :
        logger.setLevel(logging.ERROR)

    await process_cmds(MC, args, json_output)

def cli():
    try:
        asyncio.run(main(sys.argv[1:]))
    except KeyboardInterrupt:
        # This prevents the KeyboardInterrupt traceback from being shown
        print("\nExited cleanly")
    except Exception as e:
        print(f"Error: {e}")
