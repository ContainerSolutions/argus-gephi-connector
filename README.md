# argus-gephi-connector
Argus with Gephi integrated together to get real-time visualisation of infrastructure

Demo at http://container-solutions.com/?p=1856

# Installation
1. run [Gephi](https://gephi.github.io) locally (on Yosemite you will have a problem with Java version - use instructions from [here](http://sumnous.github.io/blog/2014/07/24/gephi-on-mac/)
2. via Gephi UI install [Gephi streaming plugin](https://marketplace.gephi.org/plugin/graph-streaming/)
3. turn on streaming - here is [a video](https://www.youtube.com/watch?v=TTavgM9k4oM) that shows how to do it 
4. run Argus radium on collector server - a machine that collect monitoring data from all machines
```
radium -X -d  -S argus-udp://0.0.0.0:10500 -P 10569
```
5. run Argus daemon http://qosient.com/argus/ (v3.8.1 used in the demo) on all machines to monitor
```
argus -S 5 -M 45 -i any -w argus-udp://COLLECTOR_IP:10500 -Z
```
6. install python libraries
```
pip install mock ipwhois cachetools 
```
7. copy https://github.com/panisson/pygephi_graphstreaming code to here
8. connect argus collector to Gephi by running this python script
```
ra -S COLLECTOR_IP:10569  -n -c $'\t' -M uni | python argus-gephi-connector.py
```



