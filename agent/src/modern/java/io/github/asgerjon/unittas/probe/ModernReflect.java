package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.nbt.Tag;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.ItemStack;

/**
 * What reflection (the probe core's Reflect) reaches of the version that is its own (SPEC.md 19.7 steps 4 and 6c): the
 * side's player, its level, the game (the client's Minecraft, the integrated server), an entity by its number, and its
 * stacks (with their components), entities and tags as the protocol writes them. Names are Mojang's, as the tests
 * write them. 26.x runs under them, so nothing is translated; where the game runs under other names (1.21.1's
 * obfuscated ones, Fabric's intermediary ones before 26.1, Forge 1.20.1's SRG members of Mojang's classes), each name
 * is translated by the names' lookup (Members), class by class: a class, a field of the class that declares it, a
 * method by its declaring class and parameters. A game class that doesn't declare a name has nothing by it, so a name
 * is never matched against a running one it merely spells.
 */
final class ModernReflect implements Reflect.Game {

	@Override
	public ClassLoader loader() {
		return MinecraftServer.class.getClassLoader();
	}

	@Override
	public Object player(Call call) throws ProbeException {
		return ModernThings.player(call);
	}

	@Override
	public Object world(Object player) {
		return ((Entity) player).level();
	}

	@Override
	public Object minecraft(Call call) {
		Minecraft mc = Minecraft.getInstance();
		return call.side == Side.CLIENT ? mc : mc.getSingleplayerServer();
	}

	@Override
	public Object entity(Call call, int id) throws ProbeException {
		return ModernThings.player(call).level().getEntity(id);
	}

	@Override
	public Class<?> stackType() {
		return ItemStack.class;
	}

	@Override
	public Object stack(Call call, JsonObject item) throws ProbeException {
		return ModernValues.stack(item, ModernThings.registries(call));
	}

	@Override
	public JsonElement value(Call call, Object value) throws ProbeException {
		if (value instanceof ItemStack) {
			return ModernValues.item((ItemStack) value, ModernThings.registries(call));
		}
		if (value instanceof Entity) {
			return ModernValues.entity((Entity) value);
		}
		if (value instanceof Tag) {
			// 26.3's tags write themselves as SNBT
			return Json.of(value.toString());
		}
		return null;
	}

	@Override
	public String runningClass(String binaryName) {
		return Members.runningClass(binaryName);
	}

	@Override
	public String readableClass(Class<?> type) {
		return Members.className(type);
	}

	@Override
	public String fieldName(Class<?> declaring, String name) {
		return Members.runningField(declaring, name);
	}

	@Override
	public boolean methodNamed(java.lang.reflect.Method method, String name) {
		return Members.isMethod(method, name);
	}
}
