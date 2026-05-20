### Old instructions

The instructions below apply to older versions of this application and hopefully are no longer necessary.

1. Attempt to open the app (it will fail).
2. Open System Settings > Privacy & Security.
3. Scroll down to the "Security" section.
4. Click "Open Anyway" next to the notification about the blocked app. You will likely need to enter the username and password of an administrator user on the device to approve the application.

If you follow these steps and are seeing an error along the lines of "This file is damaged and can't be opened" it is typically because a false positive from your security settings. This can be fixed by opening the Terminal application (via Applications->Utilities or Spotlight search), typing `xattr -cr ` (with a space after `cr`) and then dragging and dropping the application ito the Terminal window and hitting enter. This will remove the "quarantine" setting on the application and allow you to run it again.

![MacOS
Screenshot](https://raw.githubusercontent.com/ajkessel/gedcom-navigator/main/docs/screenshots/open_anyway.png)