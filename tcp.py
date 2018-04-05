#!/usr/bin/python

from datetime import datetime
import os
import pexpect
import time

def run_test(dirname=''):
        now = datetime.now()
        metrics_filename = dirname + '/metrics_' + now.strftime(fmt) + '.txt'
        capture_filename = dirname + '/westwood_100K_metrics_' + now.strftime(fmt) + '.pcapng'
        trace_filename = dirname + '/trace_' + now.strftime(fmt) + '.txt'

        fout = open(metrics_filename, 'wt')
        fout.write(pexpect.run('ip -6 tcp_metrics list bbbb::1'))
        fout.close()

        # Connect to the server PC and start a TCP server instance
        server = pexpect.spawn('screen /dev/ttyUSB2 115200', timeout=360)
        server.sendcontrol('c')
        server.expect_exact('ubuntu@arm:~$ ')
        server.sendline('sock -6 -i -r 32768 -R 233016 -s -A -T 6666')

        # Connect to the client PC and start packet capture
        capture = pexpect.spawn('/bin/bash', timeout=10)
        capture.expect_exact('mlainani@orion:~$')
        cmd = 'tshark -i eth6 -w ' + capture_filename + ' host bbbb::1 and tcp'
        capture.sendline(cmd)

        # Start TCP client and wait for it to finish
        # Transfering 1MB normally takes about 240secs (4mins) 
        client = pexpect.spawn('/bin/bash', timeout=360)
        client.expect_exact('mlainani@orion:~$ ')
        client.sendline('sock -6 -i -n 1 -w 1000000 -S 500000 -X 1060 bbbb::1 6666')
        ret = client.expect_exact('mlainani@orion:~$ ')
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
        ret = capture.expect_exact('mlainani@orion:~$ ')
        if ret == 0:
                print 'Packet capture was stopped\n'
        capture.kill(1)

        # Analyse TCP connection
        cmd = 'tcptrace -Wl ' + capture_filename
        fout = open(trace_filename, 'wt')
        fout.write(pexpect.run(cmd))
        fout.close()

if __name__ == "__main__":
        # Create data collection directory
        now = datetime.now()
        fmt = '%b%d-%H-%M'
        dirname = '/home/mlainani/keepme/tcp_' + now.strftime(fmt)
        os.mkdir(dirname)

        for num in range(10):
                print 'Iteration number ' + str(num)
                run_test(dirname)
                time.sleep(15)
