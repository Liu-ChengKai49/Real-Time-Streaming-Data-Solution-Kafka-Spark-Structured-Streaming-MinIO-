# Dockerfile
FROM jupyter/scipy-notebook:python-3.11  # avoid "latest" for reproducibility
USER root
RUN apt-get update -y \
 && apt-get install -y --no-install-recommends openjdk-11-jre-headless \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
ENV PATH=$JAVA_HOME/bin:$PATH

# Optional: pin PySpark so notebooks always get the same Spark
# RUN pip install --no-cache-dir pyspark==3.5.1 py4j==0.10.9.7

USER ${NB_UID}
