#!/bin/bash
set -e
cd ~/wangxu/silifuzz
mkdir -p ~/wangxu/silifuzz/output

COV_FLAGS_FILE="/home/sdc/.cache/bazel/_bazel_sdc/9c44e31f064eab4e9ff246ec08692ec6/external/fuzztest+/centipede/clang-flags.txt"
FLAGS=$(xargs < "${COV_FLAGS_FILE}" | sed -e 's/,/\\,/g' -e 's/ /,/g')

echo "Building unicorn_aarch64 with coverage flags..."
# Using --jobs=32 to prevent MCE/Hardware reset due to extreme CPU load on 128 cores
bazelisk build --jobs=32 -c opt --copt=-UNDEBUG --dynamic_mode=off \
  --per_file_copt="unicorn/.*@${FLAGS}" @silifuzz//proxies:unicorn_aarch64

echo "Building centipede..."
bazelisk build --jobs=32 -c opt @fuzztest//centipede:centipede

echo "Building silifuzz_centipede (instruction-aware mutator)..."
bazelisk build --jobs=32 -c opt @silifuzz//fuzzer:silifuzz_centipede

echo "Running centipede fuzzing with instruction-aware mutator (10,000 runs)..."
# silifuzz_centipede wraps the centipede driver and replaces the default byte
# mutator with the AArch64 instruction-aware one (program_aarch64.cc: keeps
# branch displacements pointing at instruction boundaries across
# insert/delete/swap mutations). --arch=aarch64 enables it; without it the
# wrapper falls back to byte mutation.
# Limit to 10 parallel fuzzing jobs instead of 30 to keep load reasonable
bazel-bin/fuzzer/silifuzz_centipede \
  --arch=aarch64 \
  --binary="$(pwd)/bazel-bin/proxies/unicorn_aarch64" \
  --workdir=/tmp/centipede_wd \
  -j=10 --num_runs=10000

echo "Converting raw fuzzing inputs to SDC runnable corpus..."
bazel-bin/tools/simple_fix_tool_main \
  --num_output_shards=10 \
  --output_path_prefix=/home/sdc/wangxu/silifuzz/output/runnable-corpus \
  --runner=/usr/local/bin/reading_runner_main_nolibc \
  /tmp/centipede_wd/corpus.*

echo "Generating shard list and metadata..."
ls -1 /home/sdc/wangxu/silifuzz/output/runnable-corpus.* > /home/sdc/wangxu/silifuzz/output/shard_list
echo 'version: "local_corpus"' > /home/sdc/wangxu/silifuzz/output/corpus_metadata

echo "Automated SDC deployment completed successfully."
