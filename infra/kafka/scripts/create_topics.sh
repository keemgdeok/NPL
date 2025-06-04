#!/bin/bash

# 토픽 생성 스크립트
# 이 스크립트는 topics.yml 파일의 정의에 따라 Kafka 토픽을 생성합니다.

set -e

KAFKA_HOME=${KAFKA_HOME:-/usr/bin}
CONFIG_DIR=${CONFIG_DIR:-/config}
TOPICS_FILE=${TOPICS_FILE:-${CONFIG_DIR}/topics.yml}

# 카프카가 이미 준비되었는지 확인합니다.
# echo "Checking if Kafka is ready..."
# kafka-broker-api-versions --bootstrap-server kafka:29092

# YQ가 설치되어 있지 않아서 파이썬 스크립트로 YAML 파일을 파싱합니다.
if [ ! -f "$TOPICS_FILE" ]; then
    echo "Error: Topics file not found at $TOPICS_FILE"
    exit 1
fi

# topics.yml 파일 대신 topics.json 파일을 직접 사용합니다.
TOPICS_JSON_FILE=${CONFIG_DIR}/topics.json

if [ -f "$TOPICS_JSON_FILE" ]; then
    echo "Using JSON topic definition file at $TOPICS_JSON_FILE"
    
    # jq 명령으로 JSON 파일을 파싱합니다. (jq가 없으면 설치 필요)
    if command -v jq >/dev/null 2>&1; then
        echo "Parsing topics from JSON using jq"
        TOPICS=$(jq -r '.topics[].name' $TOPICS_JSON_FILE)
        
        for TOPIC in $TOPICS; do
            PARTITIONS=$(jq -r ".topics[] | select(.name == \"$TOPIC\") | .partitions" $TOPICS_JSON_FILE)
            REPLICATION=$(jq -r ".topics[] | select(.name == \"$TOPIC\") | .replication_factor" $TOPICS_JSON_FILE)
            
            echo "Creating topic: $TOPIC (partitions: $PARTITIONS, replication: $REPLICATION)"
            
            # 토픽이 이미 존재하는지 확인합니다.
            if kafka-topics --bootstrap-server kafka:29092 --list | grep -q "^$TOPIC$"; then
                echo "Topic $TOPIC already exists, skipping creation"
            else
                kafka-topics --bootstrap-server kafka:29092 --create \
                    --topic $TOPIC \
                    --partitions $PARTITIONS \
                    --replication-factor $REPLICATION
                
                echo "Topic $TOPIC created successfully"
            fi
        done
    else
        echo "jq is not installed. Using simple grep pattern matching."
        # topics.json 파일을 수동으로 파싱합니다.
        cat $TOPICS_JSON_FILE | grep -o '"name": "[^"]*"' | cut -d'"' -f4 > /tmp/topics.txt
        
        while read -r TOPIC; do
            echo "Creating topic: $TOPIC"
            # 기본값을 사용합니다.
            PARTITIONS=3
            REPLICATION=1
            
            # 토픽이 이미 존재하는지 확인합니다.
            if kafka-topics --bootstrap-server kafka:29092 --list | grep -q "^$TOPIC$"; then
                echo "Topic $TOPIC already exists, skipping creation"
            else
                kafka-topics --bootstrap-server kafka:29092 --create \
                    --topic $TOPIC \
                    --partitions $PARTITIONS \
                    --replication-factor $REPLICATION
                
                echo "Topic $TOPIC created successfully"
            fi
        done < /tmp/topics.txt
    fi
else
    # topics.yml 파일에서 직접 토픽을 생성합니다.
    echo "Using YAML topic definition file at $TOPICS_FILE"
    
    # 토픽 이름 목록을 생성합니다.
    cat $TOPICS_FILE | grep "name:" | cut -d'"' -f2 > /tmp/topics.txt
    
    # topics.txt 파일에서 각 토픽을 처리합니다.
    while read -r TOPIC; do
        echo "Creating topic: $TOPIC"
        # 기본값을 사용합니다.
        PARTITIONS=3
        REPLICATION=1
        
        # 토픽이 이미 존재하는지 확인합니다.
        if kafka-topics --bootstrap-server kafka:29092 --list | grep -q "^$TOPIC$"; then
            echo "Topic $TOPIC already exists, skipping creation"
        else
            kafka-topics --bootstrap-server kafka:29092 --create \
                --topic $TOPIC \
                --partitions $PARTITIONS \
                --replication-factor $REPLICATION
            
            echo "Topic $TOPIC created successfully"
        fi
    done < /tmp/topics.txt
fi

echo "All topics created successfully!"

# 생성된 토픽 목록을 확인합니다.
echo "Current topics in Kafka:"
kafka-topics --bootstrap-server kafka:29092 --list 