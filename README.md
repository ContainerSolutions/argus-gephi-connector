# argus-gephi-connector
Argus with Gephi integrated together to get real-time visualisation of infrastructure

Demo at http://container-solutions.com/?p=1856

# Installation
* run [Gephi](https://gephi.github.io) locally (on Yosemite you will have a problem with Java version - use instructions from [here](http://sumnous.github.io/blog/2014/07/24/gephi-on-mac/)
* via Gephi UI install [Gephi streaming plugin](https://marketplace.gephi.org/plugin/graph-streaming/)
* turn on streaming - here is [a video](https://www.youtube.com/watch?v=7SW_FDiY0sg) that shows how to do it 
* run Argus daemon http://qosient.com/argus/ (v3.8.1 used in the demo) on all machines to monitor
```
argus -d -w argus-udp://COLLECTOR_IP:10500
```
* run Argus radium on collector server - a machine that collect monitoring data from all machines
```
radium -X -d  -S argus-udp://0.0.0.0:10501 -P 10569
```
* copy https://github.com/panisson/pygephi_graphstreaming code to here
* connect argus collector to Gephi by running this python script
```
ra -S COLLECTOR_IP:10569  -n -c $'\t' -M uni | python argus-gephi-connector.py
```



