package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.entity.Entity;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.item.ItemStack;
import net.minecraft.nbt.NBTBase;
import net.minecraft.server.MinecraftServer;

import java.util.function.Supplier;

/**
 * What reflection (the probe core's Reflect) reaches of 1.7.10 that is its own: the request's player by the side's
 * hooks, its worldObj, the game, an entity by its number, and 1.7.10's stacks, entities and NBT as the protocol writes
 * them.
 */
final class ForgeReflect implements Reflect.Game {

	/** The request's player: the client's own, or on a server the one named. */
	interface Players {
		EntityPlayer of(Call call) throws ProbeException;
	}

	private final Players players;
	/** The client's Minecraft for "minecraft" on its side; null on a dedicated server. */
	private final Supplier<Object> clientGame;

	/** By the side's hooks: ClientHooks' (GameOps.player, the client's Minecraft), ServerHooks' (by name, none). */
	ForgeReflect(Players players, Supplier<Object> clientGame) {
		this.players = players;
		this.clientGame = clientGame;
	}

	/** The game's own class loader (LaunchClassLoader), which holds Minecraft's classes and the mods': both sides'. */
	@Override
	public ClassLoader loader() {
		return MinecraftServer.class.getClassLoader();
	}

	@Override
	public Object player(Call call) throws ProbeException {
		return players.of(call);
	}

	@Override
	public Object world(Object player) {
		return ((EntityPlayer) player).worldObj;
	}

	@Override
	public Object minecraft(Call call) {
		return call.side == Side.CLIENT && clientGame != null ? clientGame.get() : MinecraftServer.getServer();
	}

	@Override
	public Object entity(Call call, int id) throws ProbeException {
		return players.of(call).worldObj.getEntityByID(id);
	}

	@Override
	public Class<?> stackType() {
		return ItemStack.class;
	}

	@Override
	public Object stack(Call call, JsonObject item) throws ProbeException {
		return Values.stack(item);
	}

	@Override
	public JsonElement value(Call call, Object value) throws ProbeException {
		if (value instanceof ItemStack) {
			return Values.item((ItemStack) value);
		}
		if (value instanceof Entity) {
			return Values.entity((Entity) value);
		}
		if (value instanceof NBTBase) {
			return Json.of(Snbt.write((NBTBase) value));
		}
		return null;
	}
}
