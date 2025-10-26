# Crawler Script Improvements - Incremental Output Writing

## ✅ IMPLEMENTED (October 26, 2025)

All improvements listed below have been successfully implemented in `scripts/02_crawl_detect.py`.

## Previous Behavior
The crawler previously accumulated ALL results in memory and wrote them in one batch at the very end:
- ❌ No progress visibility during long crawls (3,000+ sites)
- ❌ If the script crashed, all progress is lost
- ❌ High memory usage for large datasets
- ❌ Can't monitor intermediate results

## New Behavior (LIVE)
The crawler now writes results incrementally as they're collected:
- ✅ Real-time progress updates every 50 sites
- ✅ Crash resilience - partial results saved if script fails
- ✅ Lower memory usage - no accumulation in RAM
- ✅ Can monitor with `tail -f data/detections.jsonl` while crawling
- ✅ Thread-safe file writing with locks

## Proposed Changes - Incremental Writing

### 1. **Open Output Files at Start (Not End)**

**Current code (around line 571):**
```python
# write jsonl
with open(out_jsonl, "w", encoding="utf-8") as f:
  for r in results:
    f.write(json.dumps(r, ensure_ascii=False) + "\n")
```

**New approach:**
```python
# Open files at the START of run() function
jsonl_file = open(out_jsonl, "w", encoding="utf-8")
csv_file = open(out_csv, "w", newline="", encoding="utf-8")
csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
csv_writer.writeheader()
```

### 2. **Write Results Immediately After Each Practice**

**Current code (around line 560):**
```python
partial = await asyncio.gather(*chunk)
results.extend(partial)  # Accumulate in memory
```

**New approach:**
```python
partial = await asyncio.gather(*chunk)
for result in partial:
  # Write to JSONL immediately
  jsonl_file.write(json.dumps(result, ensure_ascii=False) + "\n")
  jsonl_file.flush()  # Force write to disk

  # Write to CSV immediately
  csv_writer.writerow(result)
  csv_file.flush()  # Force write to disk
```

### 3. **Add File Locking for Thread Safety**

Since async operations might write concurrently, add a lock:

```python
import asyncio
import threading

# At top of run() function
write_lock = threading.Lock()

# When writing
with write_lock:
  jsonl_file.write(json.dumps(result, ensure_ascii=False) + "\n")
  jsonl_file.flush()
```

### 4. **Ensure Files are Closed Properly**

Add try/finally block in `run()` function:

```python
jsonl_file = None
csv_file = None
try:
  jsonl_file = open(out_jsonl, "w", encoding="utf-8")
  csv_file = open(out_csv, "w", newline="", encoding="utf-8")
  # ... crawler logic ...
finally:
  if jsonl_file:
    jsonl_file.close()
  if csv_file:
    csv_file.close()
```

### 5. **Add Progress Counter**

Add a counter that updates in real-time:

```python
completed = 0
total = len(practices)

for result in partial:
  completed += 1
  # Write result...

  # Print progress every 50 sites
  if completed % 50 == 0:
    print(f"[Progress] {completed}/{total} practices completed ({completed/total*100:.1f}%)")
```

## Benefits of These Changes

✅ **Real-time progress visibility** - See results as they come in
✅ **Crash resilience** - Partial results saved if script fails
✅ **Lower memory usage** - Don't accumulate all results in RAM
✅ **Better monitoring** - Can tail the JSONL file to watch progress
✅ **Streaming analysis** - Can start analyzing results before crawl completes

## Implementation Priority

1. **High Priority:** Open files at start, write incrementally (Changes #1, #2, #4)
2. **Medium Priority:** Add progress counter (Change #5)
3. **Low Priority:** Thread-safe locking if needed (Change #3)

## Testing Notes

After implementing:
1. Test with small dataset (10-20 sites) first
2. Verify CSV headers are written correctly
3. Confirm files flush properly (tail -f should show updates)
4. Test crash recovery (kill process mid-crawl, verify partial results exist)

## Files to Modify

- `scripts/02_crawl_detect.py` - Main crawler script
  - Function: `run()` starting around line 512
  - Current batch writing code: lines 571-590
