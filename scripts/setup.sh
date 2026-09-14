#!/usr/bin/env bash
# Cai dat mot lenh - W1 tieu chi: thanh vien khac dung lai duoc
set -e

cp -n .env.example .env || true
echo "Da tao .env - hay dien LLM_API_KEY roi chay: make up"
