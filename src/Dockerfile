FROM public.ecr.aws/lambda/python:3.11-arm64

RUN yum install -y gcc gfortran make openblas-devel lapack-devel

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY data_ingestion.py .
COPY model/ ./model/
