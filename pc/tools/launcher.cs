using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

// Lanzador de respaldo si PyInstaller no esta disponible.
// Requiere que INSTALAR.bat haya creado pc\.venv.
internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "pc", ".venv", "Scripts", "python.exe");
        string script = Path.Combine(root, "pc", "main.py");

        if (!File.Exists(python) || !File.Exists(script))
        {
            MessageBox.Show(
                "Falta pc\\.venv. Ejecuta INSTALAR.bat y volve a intentar.",
                "CENTRA",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return;
        }

        string argLine = "";
        foreach (string arg in args)
        {
            argLine += "\"" + arg.Replace("\"", "\\\"") + "\" ";
        }

        ProcessStartInfo info = new ProcessStartInfo();
        info.FileName = python;
        info.Arguments = "\"" + script + "\" " + argLine;
        info.WorkingDirectory = root;
        info.UseShellExecute = false;

        try
        {
            Process process = Process.Start(info);
            if (process != null)
            {
                process.WaitForExit();
                Environment.ExitCode = process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "No se pudo abrir la aplicacion:\n" + error.Message,
                "CENTRA",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }
}
