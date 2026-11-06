package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.settings.KeyBinding;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.world.EnumDifficulty;


/**
 * Back to the start before each test (README's "What tests share"), in four parts, each on the thread it belongs to.
 * The probe's client.reset, player.reset and world.reset run them, in the order PROTOCOL.md 9.5 gives; the Java
 * runner's reset runs them in that same order, so it is one reset.
 */
public final class Reset {

	/** Where the player starts: on the flat world's grass, at the spawn. */
	public static final double START_X = ServerReset.START_X;
	public static final double START_Y = ServerReset.START_Y;
	public static final double START_Z = ServerReset.START_Z;

	private Reset() {
	}

	/** The client's part, on its thread: no screen, no keys held, the first hotbar slot, Easy, first person, the HUD. */
	public static void client(Minecraft mc) {
		if (mc.currentScreen != null) {
			mc.displayGuiScreen((GuiScreen) null);
		}
		KeyBinding.unPressAllKeys();
		// the first hotbar slot, so a given item is the held one
		mc.thePlayer.inventory.currentItem = 0;
		mc.gameSettings.difficulty = EnumDifficulty.EASY;
		mc.gameSettings.thirdPersonView = 0;
		mc.gameSettings.hideGUI = false;
	}

	/** The client's own rain and thunder, on its thread, to match the server's clear weather (code on the client asks it). */
	public static void clientWeather(Minecraft mc) {
		if (mc.theWorld != null) {
			mc.theWorld.rainingStrength = mc.theWorld.prevRainingStrength = 0.0F;
			mc.theWorld.thunderingStrength = mc.theWorld.prevThunderingStrength = 0.0F;
		}
	}

	/** The player brought back to the overworld, if it was away: ServerReset's (the server thread). */
	public static boolean respawnIfAway(EntityPlayerMP player) {
		return ServerReset.respawnIfAway(player);
	}

	/** The player's part: ServerReset's (the server thread). */
	public static void player(EntityPlayerMP player, double x, double y, double z, float yaw, float pitch) {
		ServerReset.player(player, x, y, z, yaw, pitch);
	}

	/** Every dimension's part: ServerReset's (the server thread). */
	public static void world() {
		ServerReset.world();
	}
}
