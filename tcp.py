#!/usr/bin/python

import argparse
from datetime import datetime
import csv
import os
import pexpect
import re
import sys
import time

throughputs = ['Throughput (bits/sec)']

# TCP metrics lists
rtts = ['RTT']
rttvars = ['RTT var']
cwnds = ['Cwnd']
ssthreshs = ['Ssthresh']

def run_test(dirname, ifname, throughputs):
        now = datetime.now()
        metrics_filename = dirname + '/startup_metrics_' + now.strftime(fmt) + '.txt'
        capture_filename = dirname + '/westwood_1MB_' + now.strftime(fmt) + '.pcapng'
        trace_filename = dirname + '/trace_output_' + now.strftime(fmt) + '.txt'

        # Collect startup TCP metrics if any
        cmd = 'ip -6 tcp_metrics list bbbb::1'
        fout = open(metrics_filename, 'wt')
        line = pexpect.run(cmd)
        fout.write(line)
        fout.close()
        m = re.search(r'rtt\s(\d+)us\srttvar\s(\d+)us\sssthresh\s(\d+)\scwnd\s(\d+)', line)
        if m is not None:
                rtts.append(int(m.groups()[0]) / 1000)
                rttvars.append(int(m.groups()[1]) / 1000)
                ssthreshs.append(m.groups()[2])
                cwnds.append(m.groups()[3])
        else:
                rtts.append(None)
                rttvars.append(None)
                ssthreshs.append(None)
                cwnds.append(None)

        # Connect to the server PC and start a TCP server instance
        server = pexpect.spawn('screen /dev/ttyUSB2 115200', timeout=360)
        server.sendcontrol('c')
        server.expect_exact('ubuntu@arm:~$ ')
        server.sendline('sock -6 -i -r 32768 -R 233016 -s -A -T 6666')

        # Connect to the client PC and start packet capture
        capture = pexpect.spawn('/bin/bash', timeout=10)
        
        # Set command prompt to something more unique
        COMMAND_PROMPT = r"\[PEXPECT\]\$ "
        capture.sendline(r"PS1='[PEXPECT]\$ '")
        capture.expect(COMMAND_PROMPT)
        cmd = 'tshark -i ' + ifname + ' -w ' + capture_filename + ' host bbbb::1 and tcp'
        capture.sendline(cmd)

        # Start TCP client and wait for it to finish
        # Transfering 1MB with OFDM 600 normally takes about 240secs
        # (4mins) in a network comprised of two devices
        client = pexpect.spawn('/bin/bash', timeout=360)
        client.sendline (r"PS1='[PEXPECT]\$ '")
        client.expect(COMMAND_PROMPT)
        client.sendline('sock -6 -i -n 1 -w 1000000 -S 500000 -X 1060 bbbb::1 6666')
        ret = client.expect(COMMAND_PROMPT)
        if ret == 0:
                print 'Client has finished\n'
                client.kill(1)

        # Stop TCP server
        server.sendline()
        ret = server.expect_exact('ubuntu@arm:~$ ')
        if ret == 0:
                print 'Server has stopped\n'

        server.sendcontrol('a')
        server.send('k')
        server.send('y')
        server.kill(1)

        # Stop packet capture
        capture.sendcontrol('c');
        ret = capture.expect(COMMAND_PROMPT)
        if ret == 0:
                print 'Packet capture was stopped\n'
        capture.kill(1)

        # Analyse TCP connection
        cmd = 'tcptrace -Wl ' + capture_filename
        fout = open(trace_filename, 'wt')
        fout.write(pexpect.run(cmd))
        fout.close()
        for line in pexpect.run(cmd).split('\r\n'):
                m = re.search(r'\s+(\d+)\sBps.+\s+(\d+)\sBps', line)
                if m is not None:
                        # print m.groups()
                        for val in m.groups():
                                if int(val) > 0:
                                        throughputs.append(int(val))


if __name__ == "__main__":
        parser = argparse.ArgumentParser(
                formatter_class=argparse.RawDescriptionHelpFormatter,
                description='''

DESCRIPTION:

Repeatedly transfer 1MB of data a over a TCP connection while
capturing corresponding packets and logging TCP metrics on the system
where the client runs.

The script will create a directory in the user's home directory - or
in the directory specified with the -d command line switch - to
collect the packet capture files and TCP metrics logs. The directory
name is formed using the RF modulation name passed a command line
argument along with a timestamp. E.g.

  ~/tcp_ofdm600_Apr16-13-37

The script expects the user to be already logged in to the hosts
running respectively the client and server.
        
Avoid interrupting the script with Control-C. If you have to, make
sure to kill manually all the GNU Screen sub-processe possibly holding
a serial port.

EXAMPLES:

  tcp.py -i eth3 -m ofdm600

  tcp.py -d ~/somedir -i eth3 -m ofdm600

  tcp.py -d ~/somedir -i eth3 -m ofdm600 -n 3 -t 5

LIMITATIONS:

The script has many harcoded values. In particular it's making the
assumption that

- it is being run on the same host where to run the client

- the host where to run the server is accessed over a serial
connection on /dev/ttyUSB2

'''
    )
        parser.add_argument('-d', '--directory', required=False, help='the directory where to store created files (default: user\'s home directory)')
        parser.add_argument('-i', '--interface', required=True, help='the name of the interface connecting the client host to the ACT network')
        parser.add_argument('-m', '--modulation', required=True, help='the RF modulation used in the ACT network; used to form results directory name')
        parser.add_argument('-n', '--numiter', required=False, help='the number of bulk data transfers to perform (default: 10)')
        parser.add_argument('-t', '--interval', required=False, help='the interval in secs between each bulk data transfer (default: 15)')

        args = parser.parse_args()

        dirname = os.environ['HOME']
        if args.directory is not None:
                dirname = os.path.expanduser(args.directory)
                if not os.path.isdir(dirname):
                        print 'Invalid target directory: ' + args.directory
                        sys.exit(1)
                        
        ifname = args.interface
        command = '/sbin/ip -6 addr list dev ' + ifname
        (command_output, exit_status) = pexpect.run(command, withexitstatus=1)
        if exit_status != 0:
                print 'Invalid interface name: ' + ifname
                sys.exit(1)

        # Check that GNU Screen, tshark and sock are installed
        if pexpect.which('screen') is None:
                print 'Please install GNU Screen'
                sys.exit(1)
        if pexpect.which('tshark') is None:
                print 'Please install Tshark'
                sys.exit(1)
        if pexpect.which('sock') is None:
                print 'Please install W. R. Steven\'s \"sock\" from https://github.com/mlainani/sock.git'
                sys.exit(1)

        interval = 15
        if args.interval is not None:
                interval = int(args.interval)

        numiter = 10
        if args.numiter is not None:
                numiter = int(args.numiter)

        modulation_name = args.modulation

        # Create data collection directory
        now = datetime.now()
        fmt = '%b%d-%H-%M'
        dirname += '/tcp_' + modulation_name + '_' + now.strftime(fmt)
        os.mkdir(dirname)

        results_filename = dirname + '/' + modulation_name + '_' + now.strftime(fmt) + '.csv'

        for num in range(numiter):
                print 'Iteration number ' + str(num)
                run_test(dirname, ifname, throughputs)
                print throughputs
                print rtts
                print rttvars
                print ssthreshs
                print cwnds
                time.sleep(interval)

        # Create results file
        with open(results_filename, 'w') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                rows = zip(throughputs, rtts, rttvars, ssthreshs, cwnds)
                for row in rows:
                        writer.writerow(row)

                # writer.writerow(throughputs)
                # writer.writerow(rtts)
                # writer.writerow(rttvars)
                # writer.writerow(ssthreshs)
                # writer.writerow(cwnds)
