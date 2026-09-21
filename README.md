# infra

基础设施学习与实践记录。

## 用途

记录基础设施相关的学习笔记、实验代码与配置片段。

## 目录约定

```
.
├── README.md
└── .gitignore
```

## 开始使用

```bash
gh repo clone luocheng819/infra
cd infra
```

私有仓库，需要先用 `gh auth login` 登录，或用有权限的凭据。

## Git 身份配置

本仓库使用 **仓库级** 身份，与公司仓库隔离：

```bash
git config user.name  luocheng819
git config user.email luocheng819@gmail.com
```

> **换机器克隆后必须重设一次。** 仓库级配置只存在于本地 `.git/config`，
> 不会随 clone 传播。不设置就会退回全局身份（公司邮箱），导致提交无法
> 关联到 GitHub 账号。

验证当前生效的身份：

```bash
git config --get user.name
git config --get user.email
```

确认提交是否已关联到账号（`linked_user` 应为 `luocheng819`，而非 `null`）：

```bash
gh api repos/luocheng819/infra/commits \
  -q '.[] | "\(.sha[0:7])  \(.commit.author.email)  \(if .author then .author.login else "未关联" end)"'
```

## 日常提交

```bash
git add .
git commit -m "描述"
git push
```

`main` 已绑定上游，首次推送无需 `-u`。

## 凭据

曾执行 `gh auth setup-git`，为 github.com 配置了 credential helper，
因此 `fetch` / `pull` / `push` 均免密。

若在新机器上出现 `could not read Username for 'https://github.com'`，
重新执行一次即可：

```bash
gh auth setup-git
```
