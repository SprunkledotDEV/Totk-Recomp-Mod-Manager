#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdlib.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command, int show) {
    (void)instance; (void)previous; (void)command; (void)show;
    wchar_t root[32768], python[32768], script[32768];
    DWORD length = GetModuleFileNameW(NULL, root, 32768);
    if (!length || length >= 32768) return 1;
    wchar_t *slash = wcsrchr(root, L'\\');
    if (!slash) return 1;
    *slash = 0;
    if (swprintf(python, 32768, L"%ls\\mod-manager\\python\\pythonw.exe", root) < 0 ||
        swprintf(script, 32768, L"\"%ls\\mod-manager\\mod_manager.py\"", root) < 0) return 1;
    INT_PTR result = (INT_PTR)ShellExecuteW(NULL, L"open", python, script, root, SW_SHOWNORMAL);
    if (result <= 32) {
        MessageBoxW(NULL, L"Could not start the mod manager. Keep the mod-manager folder beside this launcher.",
                    L"TotK Mod Manager", MB_OK | MB_ICONERROR);
        return 1;
    }
    return 0;
}
