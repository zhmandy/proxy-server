import sys
import os
import select
import datetime
import json
import time
import threading
from socket import socket, AF_INET, SOCK_STREAM

BUFF_SIZE = 1024
# dictionary for quick query if the cache files already exsit
CACHE_LOG = {}
cache_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), 'cacheLog.json'))
# if there is cache log already, load the cache log
if os.path.isfile(cache_dir):
    with open(cache_dir, 'r') as file:
        CACHE_LOG = json.load(file)

# get lock for caching
lock = threading.Lock()


def createProxySocket(proxyPort):
    # Create socket to listen on
    # return socket

    try:
        # creating fd for proxy
        proxySock = socket(AF_INET, SOCK_STREAM)

        # lanuch proxy server
        proxySock.bind(('127.0.0.1', proxyPort))
        proxySock.listen(5)
        print("proxy server starts to listen...")
    except Exception as e:
        print("ERR[0] %s" % e)
        sys.exit(2)
    
    return proxySock


def createServSocket(servDomain, servPort):
    # creating fd for server
    # return the socket

    servSock = socket(AF_INET, SOCK_STREAM)

    try:
        servSock.connect((servDomain, servPort))
    except Exception as e:
        print("ERR[4]: %s" % e)

    return servSock


def modifyRequestAfter301(requestToServ):
    # if the request is sent after 301 error
    # additional modifications needed for fetching images

    flag = 0
    clntHeaders = requestToServ.split("\r\n")

    url = ''
    for k in range(len(clntHeaders)):
        if clntHeaders[k].split(' ')[0] == "Referer:":
            url = clntHeaders[k].split(' ')[1]
            if url[len(url) - 1:] != '/':
                flag = 1
                clntHeaders[k] = clntHeaders[k] + '/'
            break

    if not url:
        return requestToServ

    if flag:
        # two cases
        # A. the wrong GET request URI has specific domain
        # like: /xxxx/zzz.yyy.com/gb/images/b_8d5afc09.png

        # B. the wrong GET request URI has no specific domain
        # like: /xxxx/test2/elephant.png
        request = clntHeaders[0].split(' ')[1][1:]
        http = url.find("://") + 3
        startPos = url[http:].find("/") + 1
        url = url[http:][startPos:]
        # handle case A
        if '.com' in request:
            requestItem = request.split('/')
            urlItem = url.split('/')
            i = 0
            j = 0
            # rewrite the GET request
            while i < len(requestItem):
                if '.com' in requestItem[i]:
                    break
                i = i + 1
            while j < len(urlItem):
                if '.com' in urlItem[j]:
                    break
                j = j + 1
            newRequest = '/' + '/'.join(urlItem[:j] + requestItem[i:])
            clntHeaders[0] = 'GET ' + newRequest + ' ' + clntHeaders[0].split(' ')[2]
            requestToServ = "\r\n".join(clntHeaders)
        # handle case B
        else:
            requestItem = request.split('/')
            urlItem = url.split('/')
            i = 0
            # rewrite the GET request
            while i < min(len(requestItem), len(urlItem)):
                if requestItem[i] != urlItem[i]:
                    break
                i = i + 1
            newRequest = '/' + '/'.join(urlItem + requestItem[i:])
            clntHeaders[0] = 'GET ' + newRequest + ' ' + clntHeaders[0].split(' ')[2]
            requestToServ = "\r\n".join(clntHeaders)

    return requestToServ


def parseClntRequest(msgToProxy, Host):
    # parse client request
    # rewrite the client request and send it to server

    clntHeaders = msgToProxy.split("\r\n")
    requestLine = clntHeaders[0].split(" ")
    # get HTTP version
    verHttp = requestLine[2].split("/")[1]
    
    # get URL, excluding '/' at the beginning
    path = requestLine[1][1:]
    if path[len(path)-1:] == '/':
        path += 'index.html'

    # update HOST in header with info got from Referer
    # Host will change from localhost:8080 to correct domain
    domainUpdate = ''
    for k in range(len(clntHeaders)):
        if clntHeaders[k].split(' ')[0] == "Referer:":
            url = clntHeaders[k].split(' ')[1]
            # get referer. get rid of localhost:8080/
            http = url.find("://") + 3
            startPos = url[http:].find("/") + 1
            clntHeaders[k] = "Referer: %s" % (url[:http] + url[http:][startPos:])
            domainUpdate = url[http:][startPos:].split('/')
            break

    # update Host from last connection if it is unreasonable
    if domainUpdate:
        if 'localhost' in Host or 'www' not in Host:
            for new in domainUpdate:
                if 'www.' in new:
                    Host = new
                    break

    # update domain and request
    if path.split("/")[0] == path:
        domain = path
        request = '/'
    elif 'www' not in path:
        domain = Host
        request = '/' + path
    else:
        domain = path.split("/")[0]
        request = path[len(domain):]

    # handle favicon
    if path == 'favicon.ico':
        # assign host used last time
        domain = Host
        request = '/' + path

    # modify client request header
    clntHeaders[0] = "GET " + request + " HTTP/" + verHttp
    clntHeaders[1] = "Host: %s" % domain

    requestToServ = "\r\n".join(clntHeaders)
    requestToServ = modifyRequestAfter301(requestToServ)
    print("\n-------------Request to Server:-------------\n" + requestToServ)

    return domain, requestToServ


def cacheFile(requestToServ, msgToClnt):
    # create directory
    # store the file with timesamp

    # get current path
    path = os.path.dirname(__file__)

    # create path for cached file
    lines = requestToServ.split('\r\n')
    dirs = [lines[1].split(' ')[1]]
    for item in lines[0].split(' ')[1].split('/'):
        if item is not '':
            dirs.append(item)
    # get cache name for cache log
    cacheName = '_'.join(dirs)

    for item in dirs:
        path = os.path.normpath(os.path.join(path, item))

    # create directory if not exsits
    if not os.path.exists(os.path.dirname(path)):
        try:
            os.makedirs(os.path.dirname(path))
        except Exception as e5:
            print("ERR[5] %s" % e5)
            return "error", ""

    data = msgToClnt.split(b'\r\n\r\n')[1]

    try:
        # to avoid multiple thread editing a file together
        lock.acquire()
        with open(path, 'wb') as f:
            timstamp = datetime.datetime.now().strftime("%H:%M:%S %m-%d-%Y").encode()
            f.write(timstamp)
            f.write(data)
        lock.release()
    except Exception as e6:
        print("ERR[6] %s" % e6)
        return "error", ""

    return cacheName, timstamp.decode(errors='ignore')


def checkCache(requestToServ):
    # check request
    # if files are already cached, return directory path

    lines = requestToServ.split('\r\n')
    # make sure the request is requesting a file
    check = lines[0].split(' ')[1].split('/')
    if 'www' in check[len(check)-1]:
        return None

    dirs = [lines[1].split(' ')[1]]
    for item in lines[0].split(' ')[1].split('/'):
        if item is not '':
            dirs.append(item)
    # get cache name for cache log
    cacheName = '_'.join(dirs)

    # use CACHE_LOG for quick query
    key = CACHE_LOG.get(cacheName, None)
    if key:
        # get current path
        path = os.path.dirname(__file__)
        for item in dirs:
            path = os.path.normpath(os.path.join(path, item))
        return path
    else:
        return None


def sendCache(path, clntSock):

    ftype = path.split('.')[-1]
    with open(path, 'rb') as ff:
        data = ff.read()

    # get rid of timestamp
    timestamp = data[:19].decode(errors='ignore')
    data = data[19:]

    # get correct Content-Type
    content = ''
    if ftype == 'png':
        content = 'image/png'
    elif ftype == 'jpg':
        content = 'image/jpeg'
    elif ftype == 'html':
        content = 'text/html'
    elif ftype == 'ico':
        content = 'image/x-icon'

    # get correct header
    if ftype == 'html':
        header = 'HTTP/1.0 200 OK\r\nDate: %s\r\nServer: Apache\r\nLast-' \
                 'Modified: %s\r\nAccept-Ranges: bytes\r\nVary: Accept-' \
                 'Encoding,User-Agent\r\nContent-Encoding: gzip\r\nContent-' \
                 'Length: %d\r\nKeep-Alive: timeout=15, max=97\r\nConn' \
                 'ection: Keep-Alive\r\nContent-Type: %s\r\n\r\n' % (
                     time.strftime("%a, %d %b %Y %I:%M:%S GMT", time.gmtime()),
                     time.strftime("%a, %d %b %Y %I:%M:%S GMT",
                                   time.gmtime(time.mktime(time.strptime(timestamp, "%H:%M:%S %m-%d-%Y")))),
                     len(data), content)
    else:
        header = 'HTTP/1.0 200 OK\r\nDate: %s\r\nServer: Apache\r\nLast-' \
                 'Modified: %s\r\nAccept-Ranges: bytes\r\nContent-Length: %d\r\nVary: Accept-' \
                 'User-Agent\r\nKeep-Alive: timeout=15, max=97\r\nConn' \
                 'ection: Keep-Alive\r\nContent-Type: %s\r\n\r\n' % (
                     time.strftime("%a, %d %b %Y %I:%M:%S GMT", time.gmtime()),
                     time.strftime("%a, %d %b %Y %I:%M:%S GMT",
                                   time.gmtime(time.mktime(time.strptime(timestamp, "%H:%M:%S %m-%d-%Y")))),
                     len(data), content)

    print("\n-------------Send Cache:-------------\n" + header)
    clntSock.sendall(header.encode() + data)


def handle301(servSock, responseHeader, responseStatus):
    # handle 301 error

    redirect = ''
    for line in responseHeader.split('\r\n'):
        if line.split(' ')[0] == 'Location:':
            redirect = line.split(' ')[1]
            break

    # get new domain and request for redirect request
    redirect = redirect[redirect.find('://') + 3:]
    reDomain = redirect[:redirect.find('/')]
    reRequest = redirect[redirect.find('/'):]
    if reRequest[len(reRequest) - 1:] == '/':
        reRequest += 'index.html'

    # update original request
    clntLines = requestToServ.split('\r\n')
    requestLine = clntLines[0].split(' ')
    requestLine[1] = reRequest
    clntLines[0] = ' '.join(requestLine)

    for j in range(len(clntLines)):
        if clntLines[j].split(' ') == 'Host:':
            hostLine = clntLines[j].split(' ')
            hostLine[1] = reDomain
            clntLines[j] = ' '.join(hostLine)
            break

    reRequestToServ = '\r\n'.join(clntLines)
    print("\n-------------Resend Request to Server:-------------\n" + reRequestToServ)
    servSock.close()
    childProxy(reDomain, reRequestToServ, clntSock, servPort)


def handle200(responseHeader, msgToClnt, servSock, clntSock, requestToServ):
    # handle 200, send header and data back to client

    # get content length
    byteTotal = ''
    lines = responseHeader.split('\r\n')
    for i in range(len(lines)):
        if lines[i].split(' ')[0] == 'Content-Length:':
            byteTotal = lines[i].split(' ')[1]
            break

    # get header length
    headerLength = len(msgToClnt.split(b'\r\n\r\n')[0])
    byteTogo = int(byteTotal) - (len(msgToClnt) - headerLength - 4)

    # get the rest of data
    servSock.settimeout(5)
    while byteTogo > 0:
        tmp = servSock.recv(BUFF_SIZE)
        byteTogo -= len(tmp)
        msgToClnt += tmp

    # cache the file, only happens during the first fetch
    cacheName, timstamp = cacheFile(requestToServ, msgToClnt)
    # add the name of cached file for faster query
    if cacheName != 'error' and timstamp != 'error':
        CACHE_LOG[cacheName] = timstamp
    # to avoid race condition
    lock.acquire()
    with open(cache_dir, 'w') as file:
        file.seek(0)
        json.dump(CACHE_LOG, file)
    lock.release()

    # send response (header and data) to client
    clntSock.sendall(msgToClnt)


def childProxy(servDomain, requestToServ, clntSock, servPort):
    # check cache
    # send request to server
    # handle server response
    # send data back to client

    path = checkCache(requestToServ)
    if path:
        sendCache(path, clntSock)
    else:
        servSock = createServSocket(servDomain, servPort)
        servSock.sendall(requestToServ.encode())

        # receive conditional GET response
        msgToClnt = servSock.recv(BUFF_SIZE)
        msgConditional = msgToClnt.decode(errors='ignore')

        # get response status
        responseHeader = msgConditional.split('\r\n\r\n')[0]
        print("\n-------------Response from Server:-------------\n" + responseHeader)
        responseStatus = responseHeader.split('\r\n')[0].split(' ')[1]
        print("\n-------------Status Code:-------------\n" + responseStatus)

        # handle 404 error
        if responseStatus == '404':
            clntSock.sendall(msgToClnt)
            servSock.close()
        # handle 301 error
        elif responseStatus == '301':
            handle301(servSock, responseHeader, responseStatus)
        # handle response when 200 OK
        elif responseStatus == '200':
            handle200(responseHeader, msgToClnt, servSock, clntSock, requestToServ)
            servSock.close()

    clntSock.close()


if __name__ == '__main__':

    if len(sys.argv) < 2:
        print("USAGE: proxy.py <Listen-Port>")
        sys.exit(1)
    
    # initial parameters
    proxyPort = int(sys.argv[1])
    servPort = 80
    Host = None

    # create proxy socket
    proxySock = createProxySocket(proxyPort)

    while True:
        # build connection with client
        clntSock, clntAddr = proxySock.accept()
        print("Got a connection from: ", clntAddr)
        readable, _, _ = select.select([clntSock], [], [])

        if readable:
            try:
                # get client request
                msgToProxy = clntSock.recv(BUFF_SIZE).decode(errors='ignore')
                if not msgToProxy:
                    clntSock.close()
                    print("ERR[1]: no message, disconnect client")
                else:
                    print("\n-------------Message from Client-------------: \n" + msgToProxy)
                    serverDomain, requestToServ = parseClntRequest(msgToProxy, Host)
                    # keep track the Host used last time
                    Host = serverDomain
                    threading.Thread(target=childProxy, args=(serverDomain, requestToServ, clntSock, servPort)).start()
            except Exception as e:
                # close socket, all future operations on this socket will fail
                clntSock.close()
                print("ERR[3]: %s" % e)
