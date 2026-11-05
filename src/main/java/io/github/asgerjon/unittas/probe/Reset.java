package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.settings.KeyBinding;
import net.minecraft.entity.Entity;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.WorldServer;
import net.minecraft.world.WorldSettings;

import java.util.ArrayList;

/**
 * Back to the start before each test (README's "What tests share"), in four parts, each on the thread it belongs to.
 * The probe's client.reset, player.reset and world.reset run them, in the order PROTOCOL.md 9.5 gives; the Java
 * runner's reset runs them in that same order, so it is one reset.
 */
public final class Reset {

	/** Where the player starts: on the flat world's grass, at the spawn. */
	public static final double START_X = 0.5;
	public static final double START_Y = 4.0;
	public static final double START_Z = 0.5;

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

	/**
	 * A player left in another dimension, on the server thread: back to the overworld as the End's exit takes it (the
	 * only way out of the End), which makes a new player entity. Whether it went; the client arrives some ticks later.
	 */
	public static boolean respawnIfAway(EntityPlayerMP player) {
		if (player.dimension == 0) {
			return false;
		}
		// the connection must take the new entity, as vanilla's respawn request does; otherwise the client's packets
		// keep going to the removed one
		player.playerNetServerHandler.playerEntity = MinecraftServer.getServer().getConfigurationManager()
			.recreatePlayerEntity(player, 0, true);
		return true;
	}

	/** The player's part, on the server thread, for a player in the overworld. */
	public static void player(EntityPlayerMP player, double x, double y, double z, float yaw, float pitch) {
		// the client's container, not only its screen (closed on the client): a creative inventory left open keeps window
		// 0, and the player's own slot updates would land in its grid; the close packet makes the client close it, as Esc
		// does
		player.closeScreen();
		// out of a bed an earlier test left the player in, and no bed of its to respawn at
		if (player.isPlayerSleeping()) {
			player.wakeUpPlayer(true, true, false);
		}
		player.setSpawnChunk(null, false, 0);
		// the first hotbar slot on the server too, as on the client (Reset.client): set on one side only, the client
		// never sends it again (its own didn't change), and the two disagree on what is held
		player.inventory.currentItem = 0;
		player.inventory.clearInventory(null, -1);
		player.clearItemInUse();
		player.inventoryContainer.detectAndSendChanges();
		// the player's slots whole, after the close above: what was sent while the client had another window 0 open went
		// astray
		player.sendContainerToPlayer(player.inventoryContainer);
		player.clearActivePotions();
		// arrows from earlier tests stay drawn stuck in the player, over what the next test's shots show
		player.setArrowCountInEntity(0);
		player.setGameType(WorldSettings.GameType.CREATIVE);
		// creative keeps the player flying if it was (1.7.10's game types stop flying only outside creative)
		player.capabilities.isFlying = false;
		player.sendPlayerAbilities();
		// no experience: below level 0 clears all of it, and the player's own addExperienceLevel sends it
		player.addExperienceLevel(-(player.experienceLevel + 1));
		player.extinguish();
		player.setHealth(player.getMaxHealth());
		player.getFoodStats().addStats(20, 20.0F);
		player.fallDistance = 0.0F;
		if (player.ridingEntity != null) {
			player.mountEntity(null);
		}
		player.playerNetServerHandler.setPlayerLocation(x, y, z, yaw, pitch);
	}

	/** Every dimension's part, on the server thread: Easy, no entities but players, no lightning, clear weather held. */
	public static void world() {
		for (WorldServer world : MinecraftServer.getServer().worldServers) {
			world.difficultySetting = EnumDifficulty.EASY;
			world.setAllowedSpawnTypes(true, true);
			for (Object loaded : new ArrayList<Object>(world.loadedEntityList)) {
				if (!(loaded instanceof EntityPlayer)) {
					((Entity) loaded).setDead();
				}
			}
			world.weatherEffects.clear();
		}
		// clear weather held: 1.7.10 has no weather-cycle rule, so its timers would turn rain on mid-run (a
		// `/weather clear 10s` left 200 ticks on them, and a long run reaches the natural turn), and rain darkens the day
		// and puts out fire; tests that want weather set it themselves
		Worlds.setWeather(false, false, true);
	}
}
