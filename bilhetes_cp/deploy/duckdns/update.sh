#!/usr/bin/env bash
TOKEN=$(cat ~/.duckdns/token)
curl -s "https://www.duckdns.org/update?domains=camilaebruno,bmdpereira&token=${TOKEN}&ip=" >> ~/.duckdns/duck.log
echo "$(date -Iseconds) $(cat ~/.duckdns/duck.log | tail -c 20)" >> ~/.duckdns/duck.log
