#!/usr/bin/env osascript
-- Sync through the secured deployment entry point. SSH keys are recommended.

property project_dir : POSIX path of (path to desktop folder) & "language-violence-intervention-system"

on run argv
    tell application "Terminal"
        activate
        do script "cd " & quoted form of project_dir & " && bash scripts/deploy.sh"
    end tell
end run
