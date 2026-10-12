/** Format trusted CLI arguments as literals for the workstation's terminal. */
export function terminalCommand(arguments_: readonly string[], windows?: boolean): string {
  const powershell = windows ?? arguments_.some((value) => /^(?:[a-z]:[\\/]|\\\\)/i.test(value));
  return (
    (powershell ? '& ' : '') +
    arguments_
      .map((value) => "'" + value.replaceAll("'", powershell ? "''" : "'\\''") + "'")
      .join(' ')
  );
}
