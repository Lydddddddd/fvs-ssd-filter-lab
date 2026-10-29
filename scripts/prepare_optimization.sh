#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
course_root="${1:?Usage: prepare_optimization.sh /path/to/fvs-course-lab [optimized-source]}"
opt_repo="${2:-$course_root/systems/GateANN-dense-opt}"
commit=71e87cbf0e25c0400c0109dd25a64a7c4dccc9dd
if [[ ! -d "$opt_repo" ]]; then
  git -C "$course_root/systems/GateANN-public" worktree add --detach "$opt_repo" "$commit"
fi
[[ "$(git -C "$opt_repo" rev-parse HEAD)" == "$commit" ]]
for patch in gateann_aio_compat.patch gateann_dense_visited.patch; do
  if git -C "$opt_repo" apply --reverse --check "$project_root/patches/$patch" 2>/dev/null; then
    printf 'Already applied: %s\n' "$patch"
  else
    git -C "$opt_repo" apply --check "$project_root/patches/$patch"
    git -C "$opt_repo" apply "$project_root/patches/$patch"
  fi
done
cmake -S "$opt_repo" -B "$opt_repo/build" -DCMAKE_BUILD_TYPE=Release -DUSE_AIO=ON
cmake --build "$opt_repo/build" --target search_disk_index_yfcc -j 8
mkdir -p "$project_root/build"
c++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I "$project_root/optimization" "$project_root/tests/test_dense_visited.cpp" \
  -o "$project_root/build/test_dense_visited"
"$project_root/build/test_dense_visited"
