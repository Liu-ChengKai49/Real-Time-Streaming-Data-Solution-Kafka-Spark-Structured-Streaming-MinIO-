#!/usr/bin/env bash
set -euo pipefail
set -x

# --- Config & heap ---
export HIVE_CONF_DIR=/opt/hive/conf
export HIVE_SERVER2_HEAPSIZE="${HIVE_SERVER2_HEAPSIZE:-4096}"
# Add -Xmx to all the usual places; use defaults to avoid set -u explosions
export HADOOP_CLIENT_OPTS="-Xmx4g ${HADOOP_CLIENT_OPTS:-}"
export JAVA_TOOL_OPTIONS="-Xmx4g ${JAVA_TOOL_OPTIONS:-}"
export HIVE_SERVER2_OPTS="-Xmx4g ${HIVE_SERVER2_OPTS:-}"

# JDBC driver (verify jar exists)
ls -l /opt/hive/lib/mysql-connector-j-8.4.0.jar
export HADOOP_CLASSPATH="/opt/hive/lib/mysql-connector-j-8.4.0.jar:${HADOOP_CLASSPATH:-}"

# --- HDFS readiness & bootstrap ---
NN="hdfs://namenode:9000"
HDFS="/opt/hadoop/bin/hdfs"
DFS="$HDFS dfs -fs $NN"
DFSADMIN="$HDFS dfsadmin -fs $NN"

echo "Waiting for HDFS..."
until $DFS -ls / >/dev/null 2>&1; do
  echo "HDFS not ready; retrying..."
  sleep 2
done

$DFSADMIN -safemode wait

# Bootstrap as HDFS superuser
export HADOOP_USER_NAME=root
$DFS -mkdir -p /tmp || true
$DFS -chmod 1777 /tmp || true
WAREHOUSE=/user/hive/warehouse
$DFS -mkdir -p "$WAREHOUSE" || true
$DFS -chmod -R 777 /user/hive || true
$DFS -chown -R hive:supergroup /user/hive || true
$DFS -mkdir -p /tmp/hive || true
$DFS -chmod -R 1777 /tmp/hive || true
$DFS -mkdir -p /user/hive/external || true
$DFS -chmod -R 777 /user/hive/external || true
unset HADOOP_USER_NAME

# Local tmp/scratch (for MR local mode)
mkdir -p /tmp/hive /tmp/hadoop-$(whoami)/staging || true
chmod 1777 /tmp /tmp/hive || true

# --- Metastore schema ---
echo "Initializing Hive metastore schema (mysql)..."
if ! /opt/hive/bin/schematool -dbType mysql -info >/dev/null 2>&1; then
  /opt/hive/bin/schematool -dbType mysql -initSchema
else
  echo "Hive schema already initialized."
fi

# Quiet a beeline warning (harmless, but tidy)
mkdir -p /home/hive/.beeline || true

# --- Start Metastore (Thrift 9083) ---
echo "Starting Hive Metastore..."
/opt/hive/bin/hive --service metastore >/opt/hive/logs/metastore.out 2>&1 &

# Wait for metastore port 9083 (bash's /dev/tcp)
for i in {1..60}; do
  if (exec 3<>/dev/tcp/127.0.0.1/9083) 2>/dev/null; then
    exec 3>&-
    echo "Metastore is up."
    break
  fi
  echo "Waiting for metastore on 9083..."
  sleep 2
done

# --- Start HiveServer2 (binary Thrift 10000) ---
echo "Starting HiveServer2..."
exec /opt/hive/bin/hiveserver2 \
  --hiveconf hive.root.logger=INFO,console \
  --hiveconf hive.server2.transport.mode=binary \
  --hiveconf hive.server2.thrift.port=10000 \
  --hiveconf hive.server2.thrift.bind.host=0.0.0.0 \
  --hiveconf hive.aux.jars.path=file:///opt/hive/lib/mysql-connector-j-8.4.0.jar
