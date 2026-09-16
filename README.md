# OISS Python Reference / Verifier

這是一個給 **Fall 2026 Lab01: Out-of-Order Instruction Scheduling Solver (OISS)** 使用的 Python reference model、測資產生器與 RTL simulation harness。它可以產生 TA-compatible `input.txt`／`output.txt`、求出最佳 issue order，並實際編譯使用者的 Verilog 後檢查結果。

課程 PDF、TA 的 `PATTERN.v`／`TESTBED.v` 及官方 open patterns 不包含在公開 repository；請從合法的課程來源取得。Verifier 本身只使用 Python 標準函式庫。

## 快速開始

需求：Python 3.10 或更新版本。只有實際跑 Verilog 時才需要 Icarus Verilog。

```bash
git clone https://github.com/Russell512/oiss-python-verifier.git
cd oiss-python-verifier

# 先確認 Python model
python3 -m unittest -v tests.test_oiss

# 驗證 repository 內附的 30 筆 smoke cases
python3 -m oiss verify --input sample_cases/input.txt \
  --golden sample_cases/output.txt

# 產生 1,000 筆測資與 golden
python3 -m oiss generate --count 1000 --seed 260916 \
  --out build/oiss_random_1000 --force
```

Repository 內容：

- `oiss/`：reference model、parser、generator、RTL harness 與 CLI。
- `tests/`：不需要第三方 Python package 的 regression tests。
- `sample_cases/`：30 筆已驗證的 smoke cases，不含課程官方資料。
- `dut/`：使用者放置自己 RTL 的位置；預設忽略 `.v`／`.sv`，避免誤推作業。

安裝 Icarus Verilog：

```bash
# macOS
brew install icarus-verilog

# Ubuntu / Debian
sudo apt-get install iverilog
```

把自己的 top module 放在 `dut/OISS.v` 後：

```bash
python3 -m oiss run \
  --dut dut/OISS.v \
  --input build/oiss_random_1000/input.txt \
  --golden build/oiss_random_1000/output.txt \
  --build build/oiss_random_1000/simulation \
  --force
```

## 已確認的介面與檔案

OISS 是純組合電路：

```verilog
module OISS (
    input  [95:0] Inst_seq_I,
    input  [47:0] Inst_latency_I,
    output [23:0] Inst_order_O,
    output [8:0]  Ex_cycle
);
```

- `Inst_seq_I[i*12 +: 12]` 是原始 instruction index `i`，instruction 0 在 LSB。
- `Inst_latency_I[i*6 +: 6]` 是 opcode `i` 的 latency，順序為 ADD、SUB、MUL、DIV、LOAD、STORE、BRANCH、JUMP。
- `Inst_order_O[k*3 +: 3]` 是第 `k` 個 issue 的原始 instruction index，最先 issue 的 index 在 LSB。
- `Ex_cycle` 是該 order 的最大 finish cycle，且必須等於全域最小值。

`input.txt` 第一個十進位數字是 pattern count；每筆接著是 8 個 12-bit hexadecimal instructions，再接 8 個十進位 opcode latencies。`output.txt` 每筆只有一個十進位 minimum cycle；最佳 order 不唯一，因此 golden 不固定 order。

## Python 模型

模型完全依 `PATTERN.v` 的 checker 建立 RAW、WAR、WAW：

| opcode | ReadSet | WriteSet |
|---|---|---|
| ADD/SUB/MUL/DIV | `{rs, rt}` | `{rd}` |
| LOAD | none | `{rd}` |
| STORE | `{rd}` | none |
| BRANCH | `{rs, rt}` | none |
| JUMP | none | none |

對所有 `i < j` 的 instruction pairs，只要有 RAW、WAR 或 WAW，就建立 `Ii -> Ij`。模型枚舉所有合法 topological issue orders（最多 `8! = 40320`），並依 TA checker 的 strict-order 公式計算：

```text
start(order[0]) = 0
start(order[k]) = max(start(order[k-1]) + 1,
                      finish of every dependency predecessor)
finish(i) = start(i) + opcode_latency(i)
Ex_cycle = max(finish(i))
```

此外也重現 `PATTERN.v` 的 pseudo CPU，確認重新排序後的 registers、64-word data memory 與 PC 都等同原始 index 0..7 的執行結果。

PDF 第 4 頁最後一句提到「產生 address register 給 LOAD」，但同頁 ReadSet/WriteSet 表、第 2 頁的 immediate-address 說明及實際 `PATTERN.v` 都把 LOAD 的 `rs/rt`、STORE 的 `rs/rt` 視為 6-bit memory-address immediate。因此 verifier 以實際 checker 為準，不替 LOAD/STORE address 建 register dependency。

## 驗證 TA open patterns

將合法取得的 `input.txt`、`output.txt` 放在 `Real_Lab1/` 後，從 repository 根目錄執行：

```bash
python3 -m oiss verify \
  --input Real_Lab1/input.txt \
  --golden Real_Lab1/output.txt \
  --report build/oiss_open_report.json
```

開發時使用的 100 筆 open patterns 結果：

```text
PASS: 100/100 supplied minimum cycles
```

報告同時保存每筆 Python 找到的最佳 order、decimal minimum cycle 與 packed `Inst_order_O` hex。輸出一份方便閱讀的解答：

```bash
python3 -m oiss solve \
  --input Real_Lab1/input.txt \
  --output build/oiss_solutions.txt
```

每行格式是：

```text
minimum_cycle issue_index_0 issue_index_1 ... issue_index_7
```

## 產生大量 edge/random patterns

產生 1,000 筆可直接給 TA checker 或本專案 harness 使用的測資：

```bash
python3 -m oiss generate \
  --count 1000 \
  --seed 260916 \
  --out build/oiss_random_1000 \
  --force
```

輸出包含：

- `input.txt`：和 `Real_Lab1/input.txt` 完全相同的 TA 格式。
- `output.txt`：每筆由 exhaustive reference solver 算出的 minimum cycle。
- `solutions.txt`：minimum cycle 加上一組合法最佳 order。
- `manifest.json`：seed、dependency structure、opcode、RAW/WAR/WAW 覆蓋數及檔案 SHA-256。

Generator 會平均輪替三種 TA 保證的圖形：完全無 dependency、一條長度 2–8 的 chain、兩條涵蓋全部 8 instructions 的 disjoint chains。它也會輪替 latency 最小值、最大值、交錯邊界與 seeded random latency，涵蓋全部 8 種 opcode。每個 memory instruction 使用不同 address，避免產生規格禁止的 LOAD/STORE memory conflict。

同一組 `--seed` 和 `--count` 保證產生相同內容。產生過程會立刻重新求解、驗證最佳 order 與 pseudo-CPU；不是先寫一個未驗證的隨機 golden。

本次實際產生的 1,000 筆分布為：`none=334`、`one-chain=333`、`two-chains=333`，8 種 opcode、RAW、WAR、WAW 全部有覆蓋，重新讀檔驗證結果為 **1000/1000 通過**。

有 `OISS.v` 後可直接跑這批壓力測試：

```bash
python3 -m oiss run \
  --dut Real_Lab1/OISS.v \
  --input build/oiss_random_1000/input.txt \
  --golden build/oiss_random_1000/output.txt \
  --build build/oiss_random_1000/simulation \
  --force
```

## 測試你的 `OISS.v`

若使用者將 DUT 放成 `dut/OISS.v`，可執行：

```bash
python3 -m oiss run \
  --dut dut/OISS.v \
  --input build/oiss_random_1000/input.txt \
  --golden build/oiss_random_1000/output.txt \
  --build build/oiss \
  --force
```

這個流程會：

1. 產生連接實際四個 OISS ports 的 `tb_oiss.sv`。
2. 編譯並模擬 `OISS.v`。
3. 將每筆 `Ex_cycle` 與 `Inst_order_O` 寫入 `actual.txt`。
4. 在 Python 檢查 X/Z、0..7 permutation、RAW/WAR/WAW order、該 order 的實際 completion cycle、minimum golden 與 pseudo-CPU equivalence。
5. 寫出 `build/oiss/compare_report.json`；任一筆錯誤會 exit 1。

如果整個設計都在單一 `OISS.v`，使用者只需要提供這個檔案。若 `OISS.v` instantiate 其他 modules，請把所有 source 一起列在 `--dut` 後面：

```bash
python3 -m oiss run \
  --dut rtl/OISS.v rtl/scheduler.v rtl/dependency_graph.v \
  --input build/oiss_random_1000/input.txt \
  --golden build/oiss_random_1000/output.txt \
  --build build/oiss_random_1000/simulation \
  --force
```

若使用 `` `include`` 或 SystemVerilog package，可重複加入 include directories：

```bash
python3 -m oiss run \
  --dut rtl/OISS.sv rtl/common_pkg.sv \
  --include-dir rtl/include \
  --include-dir rtl/generated \
  --input build/oiss_random_1000/input.txt \
  --golden build/oiss_random_1000/output.txt \
  --build build/oiss_random_1000/simulation \
  --force
```

若設計用 `$readmemh`／`$readmemb`，對應的 `.mem`／`.hex` 也必須存在於 RTL 預期的相對路徑。若依賴 vendor IP、standard-cell library 或特殊 simulator primitives，單純 Icarus 可能無法模擬，需要改用課程 VCS/filelist 流程。

如果使用課程 VCS，原始流程是將 `OISS.v`、`PATTERN.v`、`TESTBED.v` 放進 TA 預期目錄，讓 `PATTERN.v` 能從 `../00_TESTBED/input.txt` 與 `output.txt` 讀檔，再執行課程提供的 `./01_run_vcs_rtl`。原 `TESTBED.v` 含 FSDB system tasks，不適合未配置 Verdi/Novas 的一般 Icarus 環境，因此本專案的 Icarus harness 不修改 TA 檔案。

## 回歸測試

只測 OISS：

```bash
python3 -m unittest -v tests.test_oiss
```

執行 repository 內全部測試：

```bash
python3 -m unittest discover -v
```

OISS 測試包含規格中的 41-cycle 範例、generator 重現性、格式 round-trip、latency/opcode/graph 覆蓋，以及無 dependency 最佳化與完整 `8!` 搜尋的交叉比對。如果 `Real_Lab1/input.txt`／`output.txt` 存在，還會驗證全部 TA open patterns；公開 repository 沒有附這兩個課程檔案時，該項會自動 skip。

發佈版在不包含 TA 檔案的乾淨環境會執行 10 項測試：**9 項通過、1 項官方測資測試自動 skip**；放入 `Real_Lab1/input.txt`／`output.txt` 後則為 **10/10 通過**。另以一個 temporary 多檔 OISS fixture 實際測過多個 `--dut` sources、`--include-dir`、bit packing 與 output parser；fixture 只驗證 harness，不代表使用者 DUT 已通過。

## 重要限制

- `output.txt` 只提供 minimum cycle，不提供 order；任何合法且達到相同 minimum 的 order 都接受。
- Python exhaustive search 適合固定的 8 instructions，不是一般大型 scheduler。
- Generated cases 遵守 PDF 宣告的三種 dependency-graph 結構；它不刻意產生規格外的任意 DAG。
- 本工具不做 synthesis、STA、area 評估，也不證明 hidden patterns 一定符合 PDF 宣告的 dependency-chain 結構。
- PDF 規定 DUT 必須純組合、top module/file 為 `OISS`/`OISS.v`、不可有 latch、clock period 不超過 100 ns、area 不超過 1,500,000 µm²，且 Verilog comments 只能用英文。
