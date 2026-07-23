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

