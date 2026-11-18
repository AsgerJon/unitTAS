package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.HolderLookup;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;

/** A client's own side (ModernClientSide), from Minecraft itself: given by ModernHooks.register. */
final class ModernClientLookup implements ModernClientSide {

	@Override
	public Object minecraft() {
		return Minecraft.getInstance();
	}

	@Override
	public Player player() throws ProbeException {
		LocalPlayer own = Minecraft.getInstance().player;
		if (own == null) {
			throw new ProbeException("NotReady", "the client has no player: no world is open", null);
		}
		return own;
	}

	@Override
	public HolderLookup.Provider registries() throws ProbeException {
		ClientLevel level = Minecraft.getInstance().level;
		if (level == null) {
			throw new ProbeException("NotReady", "the client has no world", null);
		}
		return level.registryAccess();
	}

	@Override
	public Iterable<Entity> entities(Level level) {
		return ((ClientLevel) level).entitiesForRendering();
	}

	@Override
	public int camera() {
		return Minecraft.getInstance().options.getCameraType().ordinal();
	}

	@Override
	public String gameMode() {
		Minecraft mc = Minecraft.getInstance();
		return mc.gameMode == null ? "" : mc.gameMode.getPlayerMode().getName();
	}
}
