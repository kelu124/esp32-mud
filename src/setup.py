import network
sta_if = network.WLAN(network.STA_IF)
S = 'SFR_9770'
P = 'gkk33ckmf4qay57jnhe2'
sta_if.active(True)
sta_if.connect(S, P)

# Run this again and again until you get an IP Address. If this fails your connect is likely wrong.
sta_if.ifconfig()


esptool -p /dev/ttyACM0 -b 460800 --before default_reset --after hard_reset --chip esp32c3 --no-stub write_flash --flash_mode dio --flash_size detect --flash_freq 80m 0x0 build-LOLIN_C3_MINI/bootloader/bootloader.bin 0x8000 build-LOLIN_C3_MINI/partition_table/partition-table.bin 0x10000 build-LOLIN_C3_MINI/micropython.bin


esptool --chip esp32c3 --port /dev/ttyUSB0 erase_flash
