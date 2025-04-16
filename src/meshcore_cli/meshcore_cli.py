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
    data = event.payload
    contact = MC.get_contact_by_key_prefix(data['pubkey_prefix'])
    if contact is None:
        print(f"Unknown contact with pubkey prefix: {data['pubkey_prefix']}")
        name = data["pubkey_prefix"]
    else:
        name = contact["adv_name"]
    print(f"{name}: {data['text']}")

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
            print(f"{contact["adv_name"]}> ", end="", flush=True)
            line = (await asyncio.to_thread(sys.stdin.readline)).rstrip('\n')

            if line.startswith("$") :
                args = shlex.split(line[1:])
                await process_cmds(mc, args)

            elif line.startswith("to ") :
                dest = line[3:]
                nc = mc.get_contact_by_name(dest)
                if nc is None:
                    print(f"Contact '{dest}' not found in contacts.")
                    return
                else :
                    contact = nc

            elif line == "quit" or line == "q" :
                break

            elif line == "lc" :
                it = iter(mc.contacts.items())
                c = next(it)
                print (c[1]["adv_name"], end="")
                for c in it :
                    print(f", {c[1]["adv_name"]}", end="")
                print("")

            elif line == "" :
                pass

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
                    print ("<", end="")

    except KeyboardInterrupt:
        mc.stop()
        print("Exiting cli")
    except asyncio.CancelledError:
        # Handle task cancellation from KeyboardInterrupt in asyncio.run()
        print("Exiting cli")

async def next_cmd(mc, cmds, json_output=False):
    """ process next command """
    argnum = 0
    match cmds[0] :
        case "query" | "q":
            res = await mc.commands.send_device_query()
            logger.debug(res)
            if res.type == EventType.ERROR :
                print(f"ERROR: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else :
                print("Devince info :")
                if res.payload["fw ver"] >= 3:
                    print(f" Model: {res.payload["model"]}")
                    print(f" Version: {res.payload["ver"]}")
                    print(f" Build date: {res.payload["fw_build"]}")
                print(f" Firmware version : {res.payload["fw ver"]}")

        case "get_time" | "clock" :
            if len(cmds) > 1 and cmds[1] == "sync" :
                argnum=1
                res = await mc.commands.set_time(int(time.time()))
                logger.debug(res)
                if res.type == EventType.ERROR:
                    print(f"Error setting time: {res}")
                elif json_output :
                    print(json.dumps(res.payload, indent=4))
                else :
                    print("Time set")
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

        case "sync_time"|"clock sync"|"st":
            res = await mc.commands.set_time(int(time.time()))
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error syncing time: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Time synced")

        case "set_time" :
            argnum = 1
            res = await mc.commands.set_time(cmds[1])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print (f"Error setting time: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Time synced")

        case "set_txpower"|"txp" :
            argnum = 1
            res = await mc.commands.set_tx_power(cmds[1])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "set_radio"|"rad" :
            argnum = 4
            res = await mc.commands.set_radio(cmds[1], cmds[2], cmds[3], cmds[4])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "set_name" :
            argnum = 1
            res = await mc.commands.set_name(cmds[1])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error setting name: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Name set")

        case "set":
            argnum = 2
            match cmds[1]:
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

        case "set_tuning"|"tun" :
            argnum = 2
            res = await mc.commands.set_tuning(cmds[1], cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "get_bat" | "b":
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

        case "send" :
            argnum = 2
            res = await mc.commands.send_msg(bytes.fromhex(cmds[1]), cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending message {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Message sent")

        case "msg" | "sendto" | "m" | "{" : # sends to a contact from name
            argnum = 2
            await mc.ensure_contacts()
            contact = mc.get_contact_by_name(cmds[1])
            res = await mc.commands.send_msg(contact, cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending message: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else :
                print("Message sent")

        case "chan_msg"|"ch" :
            argnum = 2
            res = await mc.commands.send_chan_msg(int(cmds[1]), cmds[2])
            logger.debug(res)
            if res.type == EventType.ERROR:
                print(f"Error sending message: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))
            else:
                print("Message sent")

        case "def_chan_msg"|"def_chan"|"dch" : # default chan
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

        case "contacts" | "lc":
            res = await mc.commands.get_contacts()
            logger.debug(json.dumps(res.payload,indent=4))
            if res.type == EventType.ERROR:
                print(f"Error asking for contacts: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

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

        case "export_myself"|"e":
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
            if res.type == EventType.ERROR:
                print(f"Error retreiving msg: {res}")
            elif json_output :
                print(json.dumps(res.payload, indent=4))

        case "sync_msgs" | "sm":
            while True:
                res = await mc.commands.get_msg()
                logger.debug(res) 
                if res.type == EventType.NO_MORE_MSGS:
                    logger.info("No more messages")
                    break
                elif res.type == EventType.ERROR:
                    logger.error(f"Error retrieving messages: {res.payload}")
                    break
                elif json_output :
                    print(json.dumps(res.payload, indent=4))
                else :
                    data = res.payload
                    ct = mc.get_contact_by_key_prefix(data['pubkey_prefix'])
                    if ct is None:
                        logger.info(f"Unknown contact with pubkey prefix: {data['pubkey_prefix']}")
                        name = data["pubkey_prefix"]
                    else:
                        name = ct["adv_name"]
                    print(f"{name}: {data['text']}")

        case "infos" | "i" :
            print(json.dumps(mc.self_info,indent=4))

        case "advert" | "a":
            res = await mc.commands.send_advert()
            logger.debug(res)
            if json_output :
                print(json.dumps(res.payload, indent=4))

        case "flood_advert":
            res = await mc.commands.send_advert(flood=True)
            logger.debug(res)
            if json_output :
                print(json.dumps(res.payload, indent=4))

        case "sleep" | "s" :
            argnum = 1
            await asyncio.sleep(int(cmds[1]))

        case "wait_msg" | "wm" :
            await mc.wait_for_event(EventType.MESSAGES_WAITING)
            res = await mc.commands.get_msg()
            logger.debug(res)
            if json_output :
                print(json.dumps(res.payload, indent=4))

        case "trywait_msg" | "wmt" :
            argnum = 1
            if await mc.wait_for_event(EventType.MESSAGES_WAITING, timeout=int(cmds[1])) :
                res = await mc.commands.get_msg()
                logger.debug(res)
                if json_output :
                    print(json.dumps(res.payload, indent=4))

        case "wmt8"|"]":
            if await mc.wait_for_event(EventType.MESSAGES_WAITING, timeout=8) :
                res = await mc.commands.get_msg()
                logger.debug(res)
                if json_output :
                    print(json.dumps(res.payload, indent=4))

        case "wait_ack" | "wa" | "}":
            res = await mc.wait_for_event(EventType.ACK, timeout = 5)
            logger.debug(res)
            if json_output :
                print(json.dumps(res.payload, indent=4))

        case "wait_login" | "wl" | "]]":
            res = await mc.wait_for_event(EventType.LOGIN_SUCCESS)
            logger.debug(res)
            if json_output :
                print(json.dumps(res.payload, indent=4))

        case "wait_status" | "ws" :
            res = await mc.wait_for_event(EventType.STATUS_RESPONSE)
            logger.debug(res)
            if json_output :
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
            if json_output :
                print(json.dumps(res.payload, indent=4))

        case _ :
            if cmds[0][0] == "@" :
                res = await mc.commands.send_cli(cmds[0][1:])
                logger.debug(res)
            else :
                logger.error(f"Unknown command : {cmds[0]}")
            
    logger.info (f"cmd {cmds[0:argnum+1]} processed ...")
    return cmds[argnum+1:]

async def process_cmds (mc, args, json_output=False) :
    cmds = args
    while len(cmds) > 0 :
        cmds = await next_cmd(MC, cmds, json_output)

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
