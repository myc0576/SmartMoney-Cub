#!/usr/bin/env bash
# ==============================================================================
# Smartmoney-Cub 统一开发环境与确定性操作工具 (Dev-Env Deterministic CLI)
#
# 核心设计（对齐公众号 Multi-Agent 降本 10 大方向之 3.1.2 确定性操作由脚本执行）：
# 1. 消除大模型在终端中反复猜测参数、环境变数与命令拼接的隐藏 token 开销
# 2. 提供统一的测试、构建、图谱检索、门禁验证与状态诊断入口
# 3. 集成 RTK CLI 压缩代理与 Graphify 代码图谱
# ==============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cmd="${1:-help}"

case "$cmd" in
  test)
    sub="${2:-all}"
    case "$sub" in
      unit)
        echo "[dev-env] 运行 Python 核心单元测试..."
        python3 -m pytest tests/ -q
        ;;
      doctor)
        echo "[dev-env] 运行 Harness Doctor 安全契约审查..."
        python3 -m smartmoney_cub_harness.cli doctor
        ;;
      gui)
       echo "[dev-env] 运行 GUI 前端测试..."
       if [ -d gui ] && [ -f gui/package.json ]; then
         (cd gui && npm test)
       else
         echo "gui 目录或测试未配置"
       fi
       ;;
      e2e)
        echo "[dev-env] 运行 Playwright E2E 端到端测试..."
        npx playwright test
        ;;
      all)
        echo "[dev-env] 顺序执行 Doctor 审查与全量测试套件..."
        python3 -m smartmoney_cub_harness.cli doctor
        python3 -m pytest tests/ -q
        echo "[dev-env] 全部测试执行完成！"
        ;;
      *)
        echo "未知测试目标: $sub (支持: all | unit | doctor | gui | e2e)"
        exit 1
        ;;
    esac
    ;;

  build)
    sub="${2:-all}"
    case "$sub" in
      gui)
        echo "[dev-env] 构建 GUI 前端静态产物..."
        (cd gui && npm run build)
        ;;
      package)
        echo "[dev-env] 构建 Python 发布包..."
        python3 -m build
        ;;
      all)
        echo "[dev-env] 构建全部 GUI 与 Python 产物..."
        (cd gui && npm run build)
        python3 -m build
        echo "[dev-env] 构建完成！"
        ;;
      *)
        echo "未知构建目标: $sub (支持: all | gui | package)"
        exit 1
        ;;
    esac
    ;;

  verify)
    echo "[dev-env] 调用 3 级门禁自动化验证流水线..."
    ./scripts/verify.sh
    ;;

  graph)
    sub="${2:-query}"
    case "$sub" in
      query)
        q="${3:-}"
        if [ -z "$q" ]; then
          echo "请指定查询关键词，例如: ./scripts/dev-env.sh graph query 'providers'"
          exit 1
        fi
        echo "[dev-env] 代码图谱检索: $q"
        graphify query "$q"
        ;;
      update)
        echo "[dev-env] 增量更新代码图谱..."
        graphify extract . --code-only --force
        ;;
      status)
        echo "[dev-env] 检查代码图谱与 Git 钩子状态..."
        graphify hook status
        if [ -f graphify-out/graph.json ]; then
          echo "图谱文件已就绪: graphify-out/graph.json ($(du -h graphify-out/graph.json | awk '{print $1}'))"
        else
          echo "图谱文件未生成，请先运行: ./scripts/dev-env.sh graph update"
        fi
        ;;
      *)
        echo "未知图谱子命令: $sub (支持: query <关键词> | update | status)"
        exit 1
        ;;
    esac
    ;;

  benchmark)
    sub="${2:-publish}"
    case "$sub" in
      publish)
        run_arg="${3:-artifacts/benchmark/run_20260919_133157_240}"
        echo "[dev-env] 发布评测跑分图像到 tracked assets/benchmark/ ..."
        python3 scripts/publish_benchmark_images.py "$run_arg"
        ;;
      run)
        echo "[dev-env] 执行金融推理基准评测 (finance-jev-v1)..."
        python3 -m smartmoney_cub_harness.cli benchmark run "${@:3}"
        ;;
      verify)
        run_arg="${3:-assets/benchmark}"
        echo "[dev-env] 验证评测运行产物完整性与防篡改哈希..."
        python3 -m smartmoney_cub_harness.cli benchmark verify "$run_arg"
        ;;
      render)
        run_arg="${3:-assets/benchmark}"
        echo "[dev-env] 重新渲染基准评测 SVG/PNG 图像..."
        python3 -m smartmoney_cub_harness.cli benchmark render "$run_arg"
        ;;
      *)
        echo "未知 benchmark 子命令: $sub (支持: publish | run | verify | render)"
        exit 1
        ;;
    esac
    ;;

  rtk)
    sub="${2:-gain}"
    case "$sub" in
      gain)
        echo "[dev-env] RTK Token 压缩节省统计:"
        rtk gain
        ;;
      status)
        echo "[dev-env] RTK 配置状态:"
        which rtk && rtk --version
        ;;
      *)
        echo "未知 RTK 子命令: $sub (支持: gain | status)"
        exit 1
        ;;
    esac
    ;;

  status)
    echo "================ Smartmoney-Cub 研发环境状态 ================"
    echo "工作目录: $ROOT"
    echo "Python:   $(python3 --version 2>/dev/null || echo '未安装')"
    echo "Node.js:  $(node -v 2>/dev/null || echo '未安装')"
    echo "Graphify: $(which graphify 2>/dev/null || echo '未安装')"
    echo "RTK:      $(which rtk 2>/dev/null || echo '未安装')"
    echo "图谱状态: $([ -f graphify-out/graph.json ] && echo '已建立' || echo '未就绪')"
    echo "Git 状态: $(git rev-parse --abbrev-ref HEAD) ($(git status --short | wc -l | tr -d ' ') 个待提交修改)"
    echo "============================================================"
    ;;

  help|*)
    cat <<'HELP'
用法: ./scripts/dev-env.sh <命令> [参数]

命令列表:
  status               - 显示当前开发环境组件与依赖就绪状态
  test [target]        - 确定性测试 (all | unit | doctor | gui | e2e)
  build [target]       - 确定性构建 (all | gui | package)
  verify               - 执行完整门禁 (./scripts/verify.sh)
  graph query <关键词> - 使用 AST 语义图谱检索代码符号与依赖关系
  graph update         - 重新扫描并更新代码图谱 (graphify extract)
  graph status         - 查看图谱与 Git 自动化钩子状态
  benchmark [cmd]      - 评测流程操作 (publish | run | verify | render)
  rtk gain             - 查看 CLI 命令 Token 压缩节省量统计
  help                 - 显示本帮助信息
HELP
    ;;
esac
