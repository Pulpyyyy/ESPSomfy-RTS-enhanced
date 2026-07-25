There are a number of services that are available for ESPSomfy RTS entities.  These services can be used in your automations to have full automated control.

# open_shade
Opens the shade completely.

# close_shade
Closes the shade completely.

# stop_shade
Stops the shade if it is moving and moves the shade to the my favorite position if it is set.

# set_shade_position
Moves the shade lift position to the specified percentage

# tilt_open
Opens the tilt completely

# tilt_close
Closes the tilt completely

# set_tilt_position
Sets at target tilt position

# set_current_position
Sets the current position without actually moving the motor

# set_current_tilt_position
Sets the current tilt position without actually moving the motor

# set_sunny
Tells a motor with a sun sensor that it is currently sunny.  If the sun flag is set this will extend an awning for instance.  When the sunny condition subsides send the set_sunny with a false parameter and it will then retract the awning.  External sensors can be used to extend and retract the motor.

# set_windy
Tells a motor that there is a dangerous wind position so that it opens.  If for instance you have an awning, retracting it in high wind will keep it from flying away.  After the wind condition has been cleared it will allow the awning to be extended by a sun condition after 12 minutes and suspend any other movement for 30 seconds.

# send_command
Sends any raw RTS protocol command to the motor.  The `command` field accepts Up, My, Down, Toggle, Prog, UpDown, MyUp, MyDown, MyUpDown, StepUp, StepDown, Flag, SunFlag, Favorite or Stop.  The optional `repeat` field (0 to 50) repeats the frame, which is useful for commands that emulate a long button press such as Prog or My.  Leaving it out, or setting it to 0, tells the device to use the repeat count configured on the motor itself.

# send_step_command
Moves the motor by one step in the given `direction` (Up or Down).  The `step_size` field sets the size of the step from 1 to 127, with 127 being the largest step.  The optional `repeat` field behaves the same as in send_command.

# reboot
Reboots the ESPSomfy RTS device.  Targets the reboot button entity of the device.

# backup
Creates a backup of the ESPSomfy RTS device configuration and stores it on the Home Assistant host.  Targets the backup button entity of the device.

**The backup file contains secrets.**  It is the very file the device restores itself from, so it holds the WiFi passphrase, the remote addresses and the rolling codes in clear text.  The integration therefore writes it with owner-only permissions (0600, in a 0700 directory) into `ESPSomfyRTS_<serverId>` inside the Home Assistant configuration directory.  That location is deliberately not `www/`, which Home Assistant serves over HTTP without authentication: never copy a backup there, and treat it like any other credential when you move it off the host.  The five most recent backups are kept, older ones are deleted on the next run.

