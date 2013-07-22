#!/usr/bin/python

"""
Server configs are assumed to be in a file called check_server_status.jason co-located with the script

Command executed on each server:

printf "Installed build version: "; <versionCommand>;
ps -eo pid,lstart,etime,args | grep <psGrepString> | grep -v 'grep <psGrepString>';

Explanation of the key-value pairs:

serverGroup:
    A thread is spawned for each server group
    That thread spawns threads for each server in the group.
    Results from these worker threads are accumulated and printed together    


"hostnamePrefix": "server1", "lowerrange": 100,  "upperrange": 103,

    These combined produces server names server1100, server1101, server1102, server1103
    All four servers are checked.

"versionCommand":

    Command used to get the build version on the server group.

"psGrepCommand":

    Used to find the line corresponding to a running process
    
"processName": "single:server2"
"processName": "multiple:-Dserver1.instanceid"

    Some servers run multiple processes, some a single process.
    How do we identify different processes in our report?
    For servers running a single process, the string right of ":" is printed for the name of the process.
    For servers running multiple processes, it is assumed that the process name appears as follows in the ps string:
    -Dserver1.instanceid=<process_name>
    In this example, the process name is passed as a -D java launcher option

"""

import subprocess, string, json, os, Queue, threading, time, random, datetime

g_sshString = """
ssh <remoteServerName> << 'ENDSSH' 2>/dev/null
printf "Installed build version: "; <versionCommand>;
ps -eo pid,lstart,etime,args | grep <psGrepString> | grep -v 'grep <psGrepString>';
ENDSSH
"""

class TaskDetails:
    pass


def get_ssh_string(versionCommand, grepString, serverName):
    customizedSshString = string.replace(g_sshString, "<remoteServerName>", serverName)
    customizedSshString = string.replace(customizedSshString, "<versionCommand>", versionCommand)
    customizedSshString = string.replace(customizedSshString, "<psGrepString>", grepString)
    return customizedSshString
    
    
def get_process_name(taskDetails, splitProcessLine):
    p1 = taskDetails.processName.split(":")[0]
    p2 = taskDetails.processName.split(":")[1]
    if p1 == "single":
        return p2
    elif p1 == "multiple":
        for processLineComponent in splitProcessLine:
            if processLineComponent.startswith(p2):
                return processLineComponent.split('=')[1]
                
                
def format_ssh_output(taskDetails, linesReturnedBySsh):
    output = ""
    for aLine in linesReturnedBySsh:
        if aLine.startswith("Installed build version"):
            output += aLine + "\n"
        elif aLine.strip():
            r = string.split(aLine);
            output += "pid: " + r[0] + "\tstarted:" + " ".join(r[1:6]) + "\telapsed: " + r[6] + "\tprocessor: " + get_process_name(taskDetails, r) + "\n"
    return output


def do_work(taskDetails):
    output = ""
    output += "HOSTNAME: " + taskDetails.serverName + "\n"
    sshString = get_ssh_string(taskDetails.versionCommand, taskDetails.psGrepCommand, taskDetails.serverName)
    proc = subprocess.Popen(sshString, shell=True, stdout=subprocess.PIPE)
    res = proc.communicate()
    output += format_ssh_output(taskDetails, string.split(res[0], '\n'));                
    proc.wait()
    return output


def server_worker_thread(serverName, taskQ, outputQ):
    taskDetails = taskQ.get()
    output = do_work(taskDetails)
    outputQ.put(output)
    taskQ.task_done()
    
    
def server_main_thread(serverGroupName, propMap, printLock):
    hostnamePrefix = propMap["hostnamePrefix"]
    lowerrange = propMap["lowerrange"]
    upperrange = propMap["upperrange"]
    versionCommand = propMap["versionCommand"]
    psGrepCommand = propMap["psGrepCommand"]
    processName = propMap["processName"]
    
    taskQ = Queue.Queue()
    outputQ = Queue.Queue()    

    for i in range(lowerrange,upperrange+1):

        serverName = hostnamePrefix + str(i)
        taskDetails = TaskDetails()
        taskDetails.serverName = serverName
        taskDetails.versionCommand = versionCommand
        taskDetails.psGrepCommand = psGrepCommand
        taskDetails.hostnamePrefix = hostnamePrefix
        taskDetails.processName = processName
                
        taskQ.put(taskDetails)
                        
        threadName = threading.currentThread().getName() + serverName
        t = threading.Thread(target=server_worker_thread, name=threadName, args=(serverName, taskQ, outputQ))
        t.start()
        
    taskQ.join()
        
    output = ""
    while True:
        try:
            output += outputQ.get_nowait()
        except Queue.Empty:
            break

    with printLock:
        print output
        pass
        


def read_n_parse_json():
    script_dir = os.path.dirname(__file__)
    abs_file_path = os.path.join(script_dir, "check_server_status.json")
    with open(abs_file_path) as f:
        return json.load(f)


def main():
    printLock = threading.RLock()
    jsondata = read_n_parse_json()
    for key in jsondata:
        t = threading.Thread(target=server_main_thread, args=(key, jsondata[key], printLock) )
        t.start()

if __name__ == '__main__':
    main()