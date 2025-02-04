# mc-cli

mc-cli.py : CLI interface to MeschCore BLE companion app

## Usage

<pre>
$ mc-cli.py &lt;args&gt; &lt;commands&gt;
</pre>

### Arguments

Arguments mostly deals with ble connection

<pre>
    -h : prints this help
    -a &lt;address&gt; : specifies device address
    -s : forces ble scan for a MeshCore device
</pre>

### Available Commands 

Commands are given after arguments, they can be chained.

 <pre>
    infos               : print informations a²²bout the node
    send &lt;key&gt; &lt;msg&gt;    : sends msg to the node with pubkey starting by key
    sendto &lt;name&gt; &lt;msg&gt; : sends msg to the node with given name
    recv                : reads next msg
    sync_msgs           : gets all unread msgs from the node
    advert              : sends advert
    contacts            : gets contact list
    sync_time           : sync time with system
    set_time &lt;epoch&gt;    : sets time to given epoch
    get_time            : gets current time
    set_name &lt;name&gt;     : sets node name
    sleep &lt;secs&gt;        : sleeps for a given amount of secs
</pre>

### Examples

<pre>
$ ./mc-cli.py -s infos
Scanning for devices
Found device : F0:F5:BD:4F:9B:AD: MeshCore
Connexion started
{'adv_type': 1, 'public_key': '54c11cff0c2a861cfc5b0bd6e4b81cd5e6ca85e058bf53932d86c87dc7a20011', 'device_loc': '000000000000000000000000', 'radio_freq': 867500, 'radio_bw': 250000, 'radio_sf': 10, 'radio_cr': 5, 'name': 'toto'}
cmd ['infos'] processed ...

$ ./mc-cli.py -a F0:F5:BD:4F:9B:AD get_time
Connexion started
Current time : 2024-05-15 12:52:53 (1715770373)
cmd ['get_time'] processed ...

$ date
Tue Feb  4 12:55:05 CET 2025

$ ./mc-cli.py -a F0:F5:BD:4F:9B:AD sync_time get_time
Connexion started
True
cmd ['sync_time'] processed ...
Current time : 2025-02-04 12:55:24 (1738670124)
cmd ['get_time'] processed ...

$ ./mc-cli.py -a F0:F5:BD:4F:9B:AD contacts
Connexion started
{}
cmd ['contacts'] processed ...

$ ./mc-cli.py -a F0:F5:BD:4F:9B:AD sleep 10 contacts
Connexion started
Advertisment received
cmd ['sleep', '10'] processed ...
{
    "flo2": {
        "public_key": "d6e43f8e9ef26b801d6f5fee39f55ad6dfabfc939c84987256532d8b94aa25dd",
        "type": 1,
        "flags": 0,
        "out_path_len": 255,
        "out_path": "00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        "adv_name": "flo2",
        "last_advert": 1738670344,
        "adv_lat": 0,
        "adv_lon": 0,
        "lastmod": 1738670354
    }
}
cmd ['contacts'] processed ...

$ ./mc-cli.py -a F0:F5:BD:4F:9B:AD sendto flo2 "Hello flo2" sleep 10
Connexion started
{'type': 1, 'expected_ack': b'9\x05\x0c\x12', 'suggested_timeout': 3260}
cmd ['sendto', 'flo2', 'Hello flo2'] processed ...
Code path update
Received ACK
Msgs are waiting
cmd ['sleep', '10'] processed ...

$ ./mc-cli.py -a F0:F5:BD:4F:9B:AD recv
Connexion started
{'type': 'PRIV', 'pubkey_prefix': 'd6e43f8e9ef2', 'path_len': 255, 'txt_type': 0, 'sender_timestamp': 1738670421, 'text': 'hi'}
cmd ['recv'] processed ...
</pre>

