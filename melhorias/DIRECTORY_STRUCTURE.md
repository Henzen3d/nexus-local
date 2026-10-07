# Nexus Local 项目目录结构

## 根目录
```
nexuslocal/
├── backend/              # Python (FastAPI) 后端
├── frontend/             # React + Vite 前端
├── melhorias/            # 📁 改进计划（用户指定目录）
├── scripts/              # 部署脚本
├── docker-compose.yml    # Docker配置
├── .env                  # 环境变量
└── *.md                  # 文档
```

## 重点目录：melhorias/

### historico-planos/（历史规划）
- `assistente-proativo-plano.md` - 实施计划（6阶段，14小时）
- `design-assistente-proativo.md` - 技术设计文档
- `brainstorm-assistente-proativo.md` - 初步构想

### novas-5-melhorias-ux/（5项UX改进）
1. `01-composer-action-pills.md` - Composer动作按钮
2. `02-slash-commands-shortcuts.md` - 斜杠命令
3. `03-reasoning-thought-stream.md` - 推理流
4. `04-bento-starter-cards.md` - Bento启动卡片
5. `05-sidebar-pins-temporal.md` - 侧边栏固定+时间分组

## 后端结构 backend/
```
backend/
├── routers/              # API路由
├── orchestration/        # 对话编排
├── projects/             # RAG项目管理
├── providers/            # LLM提供商
├── ranking/              # 模型评分
├── web_search/           # 网页搜索
└── tests/                # 测试
```

## 前端结构 frontend/
```
frontend/
├── src/
│   ├── components/       # React组件
│   ├── lib/              # 工具函数
│   ├── hooks/            # 自定义hooks
│   ├── store/            # Zustand状态管理
│   ├── api/              # API客户端
│   └── i18n/             # 国际化
└── public/               # 静态资源
```

## 部署
```bash
# 同步代码
git pull origin main

# 构建并重启
cd /home/osmar/nexuslocal
bash scripts/deploy.sh
```
