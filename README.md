# Simple Proxy Server

📡A simple proxy server written in Python

The proxy server has a timestamp-based cache enabled and is able to handle 404, 301 errors. And the server has a multi-thread functionality  for concurrency requests (see detailed description below)

## Usage

>  python3 proxy.py 8080

Note: request/response of each step will be printed into console for review

## Cache

If the website is accessed for the first time, we split the server message with `'\r\n\r\n'` to get the data. current time and date is obtained by function `datetime.datetime.now().strftime("%H:%M:%S %m-%d-%Y").encode()`, then I combine time and data together in the form of bytes and write them into local files.

I added a dictionary `CACHE_LOG` with key-value set `filename: timestamp` for quick query. so when the website is accessed again, the code will first check the dictionary rather than using OS API to check if the directory exists. Also, I saved this dictionary into a local JSON file for future use

## Error Handling

### 404

For 404 error, the proxy will just send back the server response

### 301

When getting 301 error, the proxy will modify the client request with location information extracted from 301 error response. Then after redirecting the request, the requests should be modified again for fetching images

## Favicon

For handling favicon request, I added a variable `Host` to save the last accessed domain. so when the code detects the GET request is for favicon, it will direct the request to the right domain

## Threading

I used python package `Threading`. after a new client request is modified, the code will create a new thread to handle this request:

```python
# function childProxy() will do:
# 1.check cache
# 2.sending request to server
# 3.handling error
# 4.send back data to client
threading.Thread(target=childProxy, args=(serverDomain, requestToServ, clntSock, servPort)).start()
```

also, to avoid race condition, I used `threading.Lock()` object to lock the shared files (cache files, cache log JSON files) and shared variables (Host) when the threads are trying to write data into them. The lock will be released after the writing job is done

## License

MIT License