#!/usr/bin/python

import asyncio
import sys
import json

from itertools import count, takewhile
from typing import Iterator

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

ADDRESS = "F0:F5:BD:4F:9B:AD"

class MeshCore:
    """
    Interface to a BLE MeshCore device
    """
    self_info={}
    contacts={}

    def __init__(self, address):
        self.client = BleakClient(address)

    async def connect(self):
        result = asyncio.Future()
        await self.client.connect(disconnected_callback=self.handle_disconnect)
        await self.client.start_notify(UART_TX_CHAR_UUID, self.handle_rx)

        self.loop = asyncio.get_running_loop()
        self.nus = self.client.services.get_service(UART_SERVICE_UUID)
        self.rx_char = self.nus.get_characteristic(UART_RX_CHAR_UUID)

        await self.send_appstart()

        print("Connexion started") 

    def handle_rx(self, charac: BleakGATTCharacteristic, data: bytearray):
        match data[0]:
            case 0: # ok
                if len(data) == 5 :  # an integer 
                    self.result.set_result(int.from_bytes(data[1:5], byteorder='little'))
                else:
                    self.result.set_result(True)
            case 1: # error
                self.result.set_result(False)
            case 2: # contact start
                self.contact_nb = int.from_bytes(data[1:5], byteorder='little')
                self.contacts={}
            case 3: # contact 
                c = {}
                c["public_key"] = bytes(data[1:33])
                c["type"] = data[33]
                c["flags"] = data[34]
                c["out_path_len"] = data[35]
                c["out_path"] = bytes(data[36:100])
                c["adv_name"] = data[100:132].decode().replace("\0","")
                c["last_advert"] = int.from_bytes(data[132:136], byteorder='little')
                c["adv_lat"] = int.from_bytes(data[136:140], byteorder='little')
                c["adv_lon"] = int.from_bytes(data[140:144], byteorder='little')
                c["lastmod"] = int.from_bytes(data[144:148], byteorder='little')
                self.contacts[c["adv_name"]]=c
            case 4: # end of contacts
                self.result.set_result(self.contacts)
            case 5: # self info
                self.self_info["adv_type"] = data[1]
                self.self_info["public_key"] = bytes(data[4:36])
                self.self_info["device_loc"] = bytes(data[36:48])
                self.self_info["radio_freq"] = int.from_bytes(data[48:52], byteorder='little')
                self.self_info["radio_bw"] = int.from_bytes(data[52:56], byteorder='little')
                self.self_info["radio_sf"] = data[56]
                self.self_info["radio_cr"] = data[57]
                self.self_info["name"] = data[58:].decode()
                self.result.set_result(True)
            case 6: # msg sent
                res = {}
                res["type"] = data[1]
                res["expected_ack"] = bytes(data[2:6])
                res["suggested_timeout"] = int.from_bytes(data[6:10], byteorder='little')
                self.result.set_result(res)
            case 7: # contact msg recv
                res = {}
                res["type"] = "PRIV"
                res["pubkey_prefix"] = data[1:7]
                res["path_len"] = data[7]
                res["txt_type"] = data[8]
                res["sender_timestamp"] = int.from_bytes(data[9:13], byteorder='little')
                res["text"] = data[13:].decode()
                self.result.set_result(res)
            case 8 : # chanel msg recv
                res = {}
                res["type"] = "CHAN"
                res["pubkey_prefix"] = data[1:7]
                res["path_len"] = data[7]
                res["txt_type"] = data[8]
                res["sender_timestamp"] = int.from_bytes(data[9:13], byteorder='little')
                res["text"] = data[13:].decode()
                self.result.set_result(res)
            # push notifications
            case 80:
                print ("Advertisment received")
            case 81:
                print("Code path update")
            case 82:
                print("Received ACK")
            case 83:
                print("Msgs are waiting")
            # unhandled
            case _:
                print(f"Unhandled data received {data}")

    def handle_disconnect(self, _: BleakClient):
        print("Device was disconnected, goodbye.")
        # cancelling all tasks effectively ends the program
        for task in asyncio.all_tasks():
            task.cancel()

    async def send(self, data):
        self.result = asyncio.Future()
        await self.client.write_gatt_char(self.rx_char, bytes(data), response=False)
        return await asyncio.wait_for(self.result, 5)

    async def send_appstart(self):
        b1 = bytearray(b'\x01\x03      TEST')
        return await self.send(b1)

    async def send_advert(self):
        return await self.send(b"\x07")

    async def set_name(self, name):
        return await self.send(b'\x08' + name.encode("ascii"))

    async def get_time(self):
        self.time = await self.send(b"\x05")
        return self.time

    async def get_contacts(self):
        return await self.send(b"\x04")

    async def send_msg(self, dst, msg):
        timestamp = (await self.get_time()).to_bytes(4, 'little')
        data = b"\x02\x00\x00" + timestamp + dst + msg.encode("ascii")
        return await self.send(data)

    async def get_msg(self):
        return await self.send(b"\x10")


async def test(mc):
    print("\nGetting timestamp")
    print(await mc.get_time())

    print("\nSetting name")
    print(await mc.set_name("node0"))

    print("\nGetting Contacts")
    print(await mc.get_contacts())

    print("\nSending msg")
    print(await mc.send_msg( b"\xd6\xe4?\x8e\x9e\xf2","coucou"))

async def main(args):

    mc = MeshCore(ADDRESS)
    await mc.connect()

    if len(args) < 2:
        print("Commands : send, sendto, recv, contacts, infos")
        return

    match args[1] :
        case "test" : 
            await test(mc)    
        case "send" : # sends from pubkey ... does not work for the moment
            print(await mc.send_msg(args[2].encode(), args[3]))
        case "sendto" : # sends to a name (need to get contacts first so can take time, contacts should be cached to file ...)
            await mc.get_contacts()
            print(await mc.send_msg(mc.contacts[args[2]]["public_key"][0:6], args[3]))
        case "contacts" :
            print(await mc.get_contacts())
        case "recv" :
            print(await mc.get_msg())
        case "infos" :
            print(mc.self_info)
        case "advert" :
            print(await mc.send_advert())
        case "set_name" :
            print(await mc.set_name(args[2]))

asyncio.run(main(sys.argv))
