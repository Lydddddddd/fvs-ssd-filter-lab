#include "dense_visited.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <unordered_set>

int main() {
  std::mt19937 rng(20261029);
  std::size_t checks = 0;
  for (std::uint32_t n : {0u, 1u, 63u, 64u, 65u, 100000u, 1000000u}) {
    pipeann::DenseVisited bitmap(n);
    assert(bitmap.storage_bytes() == ((static_cast<std::size_t>(n) + 63) / 64) * 8);
    std::unordered_set<std::uint32_t> reference;
    if (n) {
      for (std::uint32_t id : {0u, n - 1, n / 2, 0u, n - 1}) {
        assert(bitmap.insert(id) == reference.insert(id).second);
        ++checks;
      }
      for (std::size_t i = 0; i < 200000; ++i) {
        const std::uint32_t id = rng() % n;
        assert(bitmap.insert(id) == reference.insert(id).second);
        ++checks;
      }
      pipeann::DenseVisited next_query(n);
      assert(next_query.insert(n - 1));
      assert(!next_query.insert(n - 1));
    }
    bool rejected = false;
    try { bitmap.insert(n); } catch (const std::out_of_range &) { rejected = true; }
    assert(rejected);
  }
  std::cout << "PASS: " << checks << " differential insertions, word boundaries, query isolation, invalid IDs\n";
}
