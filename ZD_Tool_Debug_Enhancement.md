# ZD Tool - 调试增强和数据保留更新

## 🔧 问题修复概述

基于您的反馈，我已经完成了以下关键改进：

### 1. 🐛 调试功能增强
**问题**：chunk结果无法正确读取和保存
**解决方案**：
- 添加详细的调试日志系统
- 新增 `/api/zd/jobs/{job_id}/debug` 调试端点
- 前端添加调试面板和控制按钮
- 实时监控chunk处理状态和数据流

### 2. 💾 数据保留机制
**问题**：所有chunk的输出结果在任务完成后被删掉
**解决方案**：
- 完全保留原始chunk数据直到会话结束
- 在 `zd_jobs[job_id]["raw_chunk_results"]` 中存储完整的原始结果
- 每个chunk保留多个副本：`result_text`, `final_result_text`, `streaming_output`
- 通过API参数 `?include_raw=true` 可获取完整原始数据

### 3. 📝 Markdown输出支持
**问题**：chunks需要用markdown格式输出
**解决方案**：
- 集成 `marked.js` markdown渲染库
- 为每个chunk添加 Raw/Markdown 格式切换开关
- 支持实时切换显示格式
- 保持表格、列表等markdown元素的正确渲染

## 🆕 新增功能详情

### 调试面板
```
🐛 Toggle Debug  [按钮]

调试面板包含：
├── Load Debug Info    - 查看job整体状态和统计
├── Load Raw Results   - 查看所有chunk的原始输出
├── Clear             - 清空调试输出
└── Hide Debug        - 隐藏调试面板
```

### 增强的数据结构
```javascript
// 每个chunk现在包含完整的追踪信息：
{
  "chunk_id": "ck_0001",
  "status": "completed|failed|processing",
  "result_text": "最终解析的结果",
  "final_result_text": "保留副本",
  "streaming_output": "实时流式输出",
  "ai_progress": "AI generating response... (1247 chars)",
  "page_start": 1,
  "page_end": 8,
  "word_count": 4256,
  "start_time": 1635123456.789,
  "completion_time": 1635123489.123,
  "error": null
}
```

### Markdown渲染功能
- **Raw模式**：显示原始AI输出文本
- **Markdown模式**：渲染为格式化的表格和文本
- 支持实时切换，不丢失数据
- 自动识别markdown表格并正确渲染

## 🔍 调试能力

### 新增API端点
```
GET /api/zd/jobs/{job_id}/debug
- 返回详细的调试信息
- 包含chunk处理统计
- 显示数据结构完整性

GET /api/zd/jobs/{job_id}/result?include_raw=true
- 返回完整的原始chunk数据
- 用于深度调试和数据分析
```

### 调试日志输出
后端控制台现在显示详细日志：
```
[DEBUG] Starting streaming for chunk ck_0001
[DEBUG] Chunk ck_0001 completed. Result length: 2347
[DEBUG] First 500 chars: | page_number | Spelling mistakes |...
[DEBUG] Chunk ck_0001 stored in zd_results. Keys: ['chunk_id', 'status', ...]
[DEBUG] Starting merge for job abc-123
[DEBUG] Available chunks: ['ck_0001', 'ck_0002', 'ck_0003']
[DEBUG] Parsing markdown table with 15 lines
[DEBUG] Found table header at line 2: | page_number | Spelling mistakes |
[DEBUG] Parsed 8 total rows
[DEBUG] Job abc-123 marked as DONE with 8 results
```

## 🎯 使用方式

### 1. 正常使用
- 按常规方式上传PPT并开始分析
- 观察chunk的实时处理状态
- 在每个chunk中切换Raw/Markdown显示格式

### 2. 调试模式
- 点击"🐛 Toggle Debug"打开调试面板
- 使用"Load Debug Info"查看整体状态
- 使用"Load Raw Results"检查原始数据
- 查看控制台日志了解详细处理过程

### 3. 数据保留
- 所有chunk原始数据现在完全保留
- 可随时访问每个chunk的完整输出
- 支持重新处理和对比分析

## 🚀 技术改进

### 后端改进
- **流式输出捕获**：实时保存AI生成的每个字符
- **数据多重备份**：每个chunk保存多个数据副本
- **调试API**：专门的调试端点提供深度信息
- **详细日志**：完整的处理过程追踪

### 前端改进
- **实时格式切换**：Raw ↔ Markdown 无损切换
- **调试界面**：专业的调试面板和控制
- **数据可视化**：JSON格式的调试数据展示
- **用户友好**：保持界面简洁的同时提供强大功能

## 📊 预期效果

通过这些改进，现在您可以：
1. **完全透明**：看到每个chunk的详细处理过程
2. **数据完整性**：所有原始数据永久保留
3. **调试便利**：快速定位和解决问题
4. **格式灵活**：支持原始文本和美观的markdown显示
5. **专业体验**：类似IDE的调试和监控体验

现在可以进行完整的测试，通过调试面板深入了解每个chunk的处理详情！