# ZD Tool (Zero Defect) - 使用说明

## 功能概述

ZD Tool是一个AI驱动的PowerPoint演示文档检查工具，专门用于发现以下问题：
- **拼写错误**：错别字、重复字母、同音词错误等
- **语法问题**：主谓一致、时态、冠词、标点、表述问题等
- **逻辑不一致**：页面内逻辑矛盾、跨页面逻辑冲突

## 主要特性

### 🚀 双模式分析
- **快速模式**：4,000-6,500词/批，最多10页/块，成本较低，速度较快
- **精确模式**：2,500-4,000词/批，最多5页/块，跨页逻辑检查更严谨

### 🎯 多模型支持
支持多种OpenAI GPT模型：
- GPT-5 (推荐)
- GPT-5 Thinking
- GPT-4.5
- GPT-5 Pro
- GPT-4

### 📊 结果导出
- JSON格式（API）
- CSV格式（Excel兼容）
- XLSX格式（原生Excel）

## 使用流程

### 1. 文件上传
- 支持.pptx格式文件
- 拖拽或点击上传
- 自动显示文件信息和建议模式

### 2. 配置分析参数
- 选择分析模式（快速/精确）
- 选择AI模型
- 点击"开始分析"

### 3. 实时进度监控
- 解析PPT → 分块 → 发送Prompt → AI分析 → 合并结果
- 实时显示处理进度和块状态
- 支持失败块的单独重试

### 4. 查看和导出结果
- 表格形式显示所有问题
- 支持按问题类型筛选
- 一键导出为CSV/Excel

## 技术实现

### 后端架构
- **Flask Web框架**：提供RESTful API
- **python-pptx**：解析PowerPoint文件
- **OpenAI API**：AI分析引擎
- **异步处理**：支持并发分析多个块
- **内存缓存**：存储分析状态和结果

### 前端功能
- **响应式设计**：适配各种屏幕尺寸
- **拖拽上传**：便捷的文件上传体验
- **实时更新**：WebSocket-style状态轮询
- **结果筛选**：灵活的数据查看选项

### API端点
```
POST /api/zd/jobs                    # 上传文件创建任务
POST /api/zd/jobs/{job_id}/run       # 开始分析
GET  /api/zd/jobs/{job_id}          # 查询进度
GET  /api/zd/jobs/{job_id}/result   # 获取结果
POST /api/zd/jobs/{job_id}/chunks/{chunk_id}/retry  # 重试失败块
```

## 配置要求

### 环境变量 (.env文件)
```
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://chat01.ai
SECRET_KEY=your_flask_secret_key_here
```

### Python依赖
```
Flask==2.3.3
python-pptx==0.6.21
openai>=1.12.0
openpyxl==3.1.2
pandas
```

## 使用说明

1. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```

2. **配置环境变量**：
   复制`.env.template`为`.env`并填入真实的API密钥

3. **启动应用**：
   ```bash
   python app.py
   ```

4. **访问界面**：
   打开浏览器访问 `http://localhost:5000`，使用密码 `BAIN2025` 登录

5. **使用ZD Tool**：
   - 在Dashboard中点击"ZD Tool"
   - 上传.pptx文件
   - 选择分析模式和AI模型
   - 开始分析并等待结果
   - 查看问题列表并导出结果

## 注意事项

- 确保PowerPoint文件为.pptx格式
- 文件大小建议不超过100MB
- 需要有效的OpenAI API密钥
- 分析时间取决于文档长度和所选模式
- 建议在稳定网络环境下使用

## 故障排除

### 常见问题
1. **上传失败**：检查文件格式是否为.pptx
2. **API错误**：确认OpenAI API密钥配置正确
3. **分析超时**：尝试使用快速模式或分解大文件
4. **结果为空**：检查PPT是否包含可分析的文本内容

### 日志查看
应用运行时会在控制台显示详细日志，包括：
- 文件解析状态
- API调用情况
- 错误信息和堆栈跟踪

---

**开发完成**：ZD Tool已成功集成到Bain Toolbox中，替代了原有的"Writing Optimizer"功能，提供更专业的PowerPoint文档质量检查服务。