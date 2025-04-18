# meshcore-cli

meshcore-cli : CLI interface to MeschCore companion app over BLE, TCP or Serial

## Install

Meshcore-cli depends on the [python meshcore](https://github.com/fdlamotte/meshcore_py) package. You can install both via `pip` or `pipx` using the command :

 <pre>
$ pipx install meshcore-cli
</pre>

It will install you `meshcore-cli` and `meshcli`, which is an alias to the former.

If you want meshcore-cli to remember last BLE device, you should have some `$HOME/.config/meshcore` where configuration for meschcore-cli will be stored (if not it will use first device it finds).

## Usage

<pre>
$ meshcli &lt;args&gt; &lt;commands&gt;
</pre>

If using BLE, don't forget to pair your device first (using `bluetoothctl` for instance on Linux) or meshcli won't be able to communicate.

### Arguments

Arguments mostly deals with ble connection

<pre>
    -h : prints this help                                                                      
    -j : json output
    -a &lt;address&gt;    : specifies device address (can be a name)
    -d &lt;name&gt;       : filter meshcore devices with name or address
    -t &lt;hostname&gt;   : connects via tcp/ip
    -p &lt;port&gt;       : specifies tcp port (default 5000)
    -s &lt;port&gt;       : use serial port &lt;port&gt;
    -b &lt;baudrate&gt;   : specify baudrate
</pre>

### Available Commands 

Commands are given after arguments, they can be chained and some have shortcuts. Also prefixing a command with a dot ```.``` will force it to output json instead of synthetic result.

<pre>
   General commands
    chat                   : enter the chat (interactive) mode
    chat_to &lt;ct&gt;           : enter chat with contact                to
    infos                  : print informations about the node      i
    card                   : export this node URI                   e
    ver                    : firmware version                       v
    reboot                 : reboots node
    sleep &lt;secs&gt;           : sleeps for a given amount of secs      s
  Messenging
    msg &lt;name&gt; &lt;msg&gt;       : send message to node by name           m  {
    wait_ack               : wait an ack                            wa }
    chan &lt;nb&gt; &lt;msg&gt;        : send message to channel number &lt;nb&gt;    ch
    public                 : send message to public channel (0)     dch
    recv                   : reads next msg                         r
    sync_msgs              : gets all unread msgs from the node     sm
    wait_msg               : wait for a message and read it         wm
  Management
    advert                 : sends advert                           a
    floodadv               : flood advert
    get &lt;param&gt;            : gets a param, \"get help\" for more
    set &lt;param&gt; &lt;value&gt;    : sets a param, \"set help\" for more 
    time &lt;epoch&gt;           : sets time to given epoch
    clock                  : get current time
    clock sync             : sync device clock                      st
    cli                    : send a cmd to node's cli (if avail)    @
  Contacts
    contacts / list        : gets contact list                      lc
    share_contact &lt;ct&gt;     : share a contact with others            sc
    export_contact &lt;ct&gt;    : get a contact's URI                    ec
    remove_contact &lt;ct&gt;    : removes a contact from this node
    reset_path &lt;ct&gt;        : resets path to a contact to flood      rp
    change_path &lt;ct&gt; &lt;pth&gt; : change the path to a contact           cp
  Repeaters
    login &lt;name&gt; &lt;pwd&gt;     : log into a node (rep) with given pwd   l  [[ 
    wait_login             : wait for login (timeouts after 5sec)   wl ]]
    cmd &lt;name&gt; &lt;cmd&gt;       : sends a command to a repeater (no ack) c  [
    wmt8                   : wait for a msg (reply) with a timeout     ]
    req_status &lt;name&gt;      : requests status from a node            rs
    wait_status            : wait and print reply                   ws
</pre>

### Examples

<pre>
# gets info from first ble MC device it finds (was -s but now used for serial port)
$ meshcore-cli -d "" infos
INFO:meshcore:Scanning for devices
INFO:meshcore:Found device : C2:2B:A1:D5:3E:B6: MeshCore-t114_fdl
INFO:meshcore:BLE Connection started
{
    "adv_type": 1,
    "tx_power": 22,
    "max_tx_power": 22,
    "public_key": "993acd42fc779962c68c627829b32b111fa27a67d86b75c17460ff48c3102db4",
    "adv_lat": 47.794,
    "adv_lon": -3.428,
    "radio_freq": 869.525,
    "radio_bw": 250.0,
    "radio_sf": 11,
    "radio_cr": 5,
    "name": "t114_fdl"
}

# getting time
$ meshcli -a C2:2B:A1:D5:3E:B6 clock
INFO:meshcore:BLE Connection started
Current time : 2025-04-18 08:19:26 (1744957166)

# If you're familiar with meshcli, you should have noted that 
# now output is not json only, to get json output, use -j 
# or prefix your commands with a dot
$ meshcli -a C2:2B:A1:D5:3E:B6 .clock
INFO:meshcore:BLE Connection started
{
    "time": 1744957249
}

# Using -j, meshcli will return a json array of replies ...
$ meshcli -j -a C2:2B:A1:D5:3E:B6 clock
[
{
    "time": 1744957261
}
]

# So if I reboot the node, and want to set time, I can chain the commands
# and get that kind of output (even better by feeding it to jq)
$ meshcli reboot
INFO:meshcore:BLE Connection started
$ meshcli -j clock clock sync clock | jq
[
  {
    "time": 1715770360
  },
  {},
  {
    "time": 1744957460
  }
]
# Now check if time is ok with human output (I don't read epoch time yet)
$ meshcli clock
INFO:meshcore:BLE Connection started
Current time : 2025-04-18 08:26:25 (1744957585)

# Now you'll probably want to send some messages ... 
# For that, there is the msg command, wait_ack
$ meshcli msg Techo_fdl "Hello T-Echo" wa
INFO:meshcore:BLE Connection started
Msg acked

# I can check the message on the techo
$ meshcli -d Techo sm
INFO:meshcore:Scanning for devices
INFO:meshcore:Found device : DE:B6:D0:68:D5:62: MeshCore-Techo_fdl
INFO:meshcore:BLE Connection started
t114_fdl(0): Hello T-Echo

# And reply using json output for more verbosity
[
  {
    "type": 0,
    "expected_ack": "83059275",
    "suggested_timeout": 4446
  },
  {
    "code": "83059275"
  }
]

# But this could have been done easier using the chat mode
# Here from the techo side. Note that un-acked messages will be
# signaled with an ! at the start of the prompt
$ meshcli chat
INFO:meshcore:BLE Connection started
Interactive mode, most commands from terminal chat should work.
Use "to" to selects contact, "list" to list contacts, "send" to send a message ...
Line starting with "$" or "." will issue a meshcli command.
"quit" or "q" will end interactive mode
 t114_fdl(D): Hello T-Echo
EnsibsRoom> Hi
!EnsibsRoom> to t114_fdl
t114_fdl> Hi
 t114_fdl(D): It took you long to reply ...
t114_fdl> I forgot to set the recipient with the to command
 t114_fdl(D): It happens ...
t114_fdl> 

# Loging into repeaters and sending commands is also possible
# directly from the chat, because we can use meshcli commands ;)
$ meshcli chat (pending msgs are shown at connexion ...)
INFO:meshcore:BLE Connection started
Interactive mode, most commands from terminal chat should work.
Use "to" to selects contact, "list" to list contacts, "send" to send a message ...
Line starting with "$" or "." will issue a meshcli command.
"quit" or "q" will end interactive mode
 Techo_fdl(0): Cool to receive some msgs from you
 Techo_fdl(D): Hi
 Techo_fdl(D): I forgot to set the recipient with the to command
FdlRoom> $login FdlRoom password wl
Login success
FdlRoom> $cmd FdlRoom clock
 FdlRoom(0): 06:40 - 18/4/2025 UTC
FdlRoom>
</pre>



