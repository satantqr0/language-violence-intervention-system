#!/usr/bin/env osascript
-- -*- coding: utf-8 -*-
(*
  双击此文件自动部署到树莓派
  用法: 在终端运行  osascript deploy_pi.scpt
        或直接双击此文件
*)

property pi_host : "192.168.1.100"
property pi_user : "pi"
property remote_dir : "/home/pi/language-violence-intervention-system"

-- 获取桌面路径
property desktop_path : POSIX path of (path to desktop folder)
property project_dir : desktop_path & "language-violence-intervention-system"

on run argv
    tell application "Terminal"
        activate

        -- 等待终端启动
        delay 0.5

        -- 显示说明
        beep
        display dialog "即将部署到 " & pi_user & "@" & pi_host & return & return & "请确保已保存所有本地更改" buttons {"取消", "继续"} default button 2 giving up after 10
        if button returned of result is "取消" then
            return
        end if

        -- 打开新窗口执行部署
        do script "cd " & quoted form of project_dir & "
echo '========================================'
echo '  部署到树莓派中，请稍候…'
echo '========================================'
chmod +x scripts/deploy.sh
./scripts/deploy.sh
echo ''
echo '按 Enter 关闭窗口'
read"
    end tell
end run
