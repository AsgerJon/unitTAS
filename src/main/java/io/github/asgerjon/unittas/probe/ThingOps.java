package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.block.Block;
import net.minecraft.client.Minecraft;
import net.minecraft.client.audio.PositionedSoundRecord;
import net.minecraft.client.gui.GuiChat;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EntityList;
import net.minecraft.entity.EntityLiving;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.entity.player.InventoryPlayer;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.util.ResourceLocation;
import net.minecraft.world.World;

import java.io.File;
import java.io.IOException;
import java.util.Map;

/**
 * The bodies of step 6's operations (PROTOCOL.md 8.4 to 8.10), given at preInit: player.look, inventory.set, the
 * blocks, entity.spawn, .get and .remove, the keys, typing into a screen, chat.read and chat.send, camera.set,
 * sound.play, screenshot. Each body runs on its request's side; what it waits for after is its settle phase.
 */
final class ThingOps {

	private ThingOps() {
	}

	static void bind(Probe probe) {
		probe.op("player.look").does(ThingOps::look).settles(ThingOps::ticks1);
		probe.op("inventory.set").does(ThingOps::inventorySet);
		probe.op("block.get").does(ThingOps::blockGet);
		probe.op("block.set").does(ThingOps::blockSet);
		probe.op("entity.spawn").does(ThingOps::spawn);
		probe.op("entity.get").does(call -> {
			Entity entity = entity(call);
			JsonObject value = Values.entity(entity);
			if (call.flag("nbt", false)) {
				net.minecraft.nbt.NBTTagCompound data = new net.minecraft.nbt.NBTTagCompound();
				entity.writeToNBT(data);
				value.addProperty("nbt", Snbt.write(data));
			}
			return value;
		});
		probe.op("entity.remove").does(call -> {
			entity(call).setDead();
			return new JsonObject();
		});
		probe.op("key.down").does(call -> {
			Input.down(key(call));
			return new JsonObject();
		});
		probe.op("key.up").does(call -> {
			Input.up(key(call));
			return new JsonObject();
		});
		probe.op("key.tap").does(ThingOps::tapDown).settles(ThingOps::tapUp);
		probe.op("screen.type").does(ThingOps::type).settles(ThingOps::settle4);
		probe.op("screen.key").does(ThingOps::screenKey).settles(ThingOps::settle4);
		probe.op("chat.read").does(ThingOps::chatRead);
		probe.op("chat.send").does(ThingOps::chatSend).settles(ThingOps::chatLines);
		probe.op("camera.set").does(ThingOps::camera).settles((call, value) -> wait(call, 2, value));
		probe.op("sound.play").does(ThingOps::sound);
		probe.op("screenshot").does(ThingOps::screenshotBefore).settles(ThingOps::screenshotTake);
		probe.op("reflect.get").does(Reflect::get);
		probe.op("reflect.set").does(Reflect::set);
	}

	private static JsonElement wait(Call call, long ticks, JsonElement value) throws ProbeException, InterruptedException {
		try {
			Sides.get().waitTicks(Side.CLIENT, ticks, Sides.STALL_SECONDS);
		} catch (Sides.Stalled stalled) {
			throw Ops.stalled(call.probe, stalled);
		}
		return value;
	}

	private static JsonElement ticks1(Call call, JsonElement value) throws ProbeException, InterruptedException {
		return wait(call, 1, value);
	}

	private static JsonElement settle4(Call call, JsonElement value) throws ProbeException, InterruptedException {
		return wait(call, call.number("settle_ticks", 4, 0, 1200), value);
	}

	private static int[] position(Call call, String key) throws ProbeException {
		JsonElement given = call.args.get(key);
		if (given == null || !given.isJsonArray() || given.getAsJsonArray().size() != 3) {
			throw ProbeException.badRequest(key, key + " is [x, y, z]");
		}
		int[] pos = new int[3];
		for (int i = 0; i < 3; i++) {
			pos[i] = given.getAsJsonArray().get(i).getAsInt();
		}
		return pos;
	}

	// ---------------------------------------------------------------- the player and the inventory

	private static JsonElement look(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getMinecraft();
		if (mc.thePlayer == null) {
			throw new ProbeException("NotReady", "player.look needs a world", null);
		}
		if (!call.has("yaw") || !call.has("pitch")) {
			throw ProbeException.badRequest("yaw", "player.look needs yaw and pitch, in degrees");
		}
		float yaw = (float) call.args.get("yaw").getAsDouble();
		float pitch = (float) call.args.get("pitch").getAsDouble();
		Input.look(mc, yaw, pitch);
		return new JsonObject();
	}

	/** An item value (5.3) as a new stack; NotFound for an id the game doesn't have. */
	static ItemStack stack(JsonElement value) throws ProbeException {
		if (value == null || value.isJsonNull()) {
			return null;
		}
		if (!value.isJsonObject() || Json.string(value.getAsJsonObject(), "id") == null) {
			throw ProbeException.badRequest("item", "an item is {\"id\": ..., \"count\": ..., \"meta\": ...} or null");
		}
		JsonObject item = value.getAsJsonObject();
		String id = Json.string(item, "id");
		if (!Item.itemRegistry.containsKey(id)) {
			throw new ProbeException("NotFound", "this game has no item " + id, Json.object("what", id));
		}
		if (item.has("components")) {
			throw new ProbeException("Unsupported", "1.7.10's items have NBT, not components", null);
		}
		int count = item.has("count") ? item.get("count").getAsInt() : 1;
		int meta = item.has("meta") ? item.get("meta").getAsInt() : 0;
		ItemStack stack = new ItemStack((Item) Item.itemRegistry.getObject(id), count, meta);
		String nbt = Json.string(item, "nbt");
		if (nbt != null) {
			stack.setTagCompound(compound(nbt, "nbt"));
		}
		return stack;
	}

	/** A compound from SNBT; a BadRequest naming the field for text that isn't one. */
	static net.minecraft.nbt.NBTTagCompound compound(String text, String field) throws ProbeException {
		try {
			return Snbt.readCompound(text);
		} catch (IllegalArgumentException e) {
			throw ProbeException.badRequest(field, e.getMessage());
		}
	}

	private static JsonElement inventorySet(Call call) throws ProbeException {
		EntityPlayerMP player = (EntityPlayerMP) GameOps.player(call);
		JsonObject items = call.object("items");
		if (items == null) {
			if (!call.has("slot")) {
				throw ProbeException.badRequest("slot", "inventory.set needs a slot and an item, or items");
			}
			items = new JsonObject();
			items.add(call.string("slot", null), call.args.get("item"));
		}
		// every slot and item checked before any is set
		java.util.List<Object[]> changes = new java.util.ArrayList<>();
		for (Map.Entry<String, JsonElement> entry : items.entrySet()) {
			GameOps.slot(player.inventory, entry.getKey());
			changes.add(new Object[]{entry.getKey(), stack(entry.getValue())});
		}
		for (Object[] change : changes) {
			set(player, (String) change[0], (ItemStack) change[1]);
		}
		player.inventoryContainer.detectAndSendChanges();
		return new JsonObject();
	}

	/** Puts the stack in the named slot; the caller sends the changes. */
	static void set(EntityPlayerMP player, String slot, ItemStack stack) {
		InventoryPlayer inventory = player.inventory;
		if (slot.equals("held")) {
			inventory.setInventorySlotContents(inventory.currentItem, stack);
		} else if (slot.equals("cursor")) {
			inventory.setItemStack(stack);
			player.updateHeldItem();
		} else if (slot.startsWith("main.")) {
			inventory.setInventorySlotContents(Integer.parseInt(slot.substring(5)), stack);
		} else {
			String[] armor = {"armor.feet", "armor.legs", "armor.chest", "armor.head"};
			for (int i = 0; i < armor.length; i++) {
				if (armor[i].equals(slot)) {
					inventory.armorInventory[i] = stack;
				}
			}
		}
	}

	// ---------------------------------------------------------------- blocks

	private static World world(Call call) throws ProbeException {
		return GameOps.player(call).worldObj;
	}

	private static JsonElement blockGet(Call call) throws ProbeException {
		int[] pos = position(call, "pos");
		World world = world(call);
		Block block = world.getBlock(pos[0], pos[1], pos[2]);
		JsonObject value = Json.object("id", String.valueOf(Block.blockRegistry.getNameForObject(block)),
			"meta", world.getBlockMetadata(pos[0], pos[1], pos[2]));
		if (call.flag("tile", false)) {
			net.minecraft.tileentity.TileEntity tile = world.getTileEntity(pos[0], pos[1], pos[2]);
			if (tile == null) {
				value.add("tile", com.google.gson.JsonNull.INSTANCE);
			} else {
				net.minecraft.nbt.NBTTagCompound data = new net.minecraft.nbt.NBTTagCompound();
				tile.writeToNBT(data);
				value.addProperty("tile", Snbt.write(data));
			}
		}
		return value;
	}

	private static JsonElement blockSet(Call call) throws ProbeException {
		int[] pos = position(call, "pos");
		JsonObject block = call.object("block");
		String id = block == null ? null : Json.string(block, "id");
		if (id == null) {
			throw ProbeException.badRequest("block", "block is {\"id\": ..., \"meta\": ...}");
		}
		if (!Block.blockRegistry.containsKey(id)) {
			throw new ProbeException("NotFound", "this game has no block " + id, Json.object("what", id));
		}
		net.minecraft.nbt.NBTTagCompound tileData = call.has("tile") ? compound(call.string("tile", null), "tile") : null;
		int meta = block.has("meta") ? block.get("meta").getAsInt() : 0;
		String update = call.string("update", "default");
		int flags;
		switch (update) {
			case "default":
				// neighbours told, and the clients sent it, as a player's placing does
				flags = 3;
				break;
			case "none":
				// no neighbour updates; still sent, or the client would never see it
				flags = 2;
				break;
			default:
				throw ProbeException.badRequest("update", "update is default or none, not " + update);
		}
		World world = world(call);
		world.setBlock(pos[0], pos[1], pos[2], (Block) Block.blockRegistry.getObject(id), meta, flags);
		if (tileData != null) {
			net.minecraft.tileentity.TileEntity tile = world.getTileEntity(pos[0], pos[1], pos[2]);
			if (tile == null) {
				throw ProbeException.badRequest("tile", id + " has no tile entity to take the data");
			}
			// the tile's own place, whatever the data said
			tileData.setInteger("x", pos[0]);
			tileData.setInteger("y", pos[1]);
			tileData.setInteger("z", pos[2]);
			tile.readFromNBT(tileData);
			tile.markDirty();
			world.markBlockForUpdate(pos[0], pos[1], pos[2]);
		}
		return new JsonObject();
	}

	// ---------------------------------------------------------------- entities

	private static Entity entity(Call call) throws ProbeException {
		if (!call.has("entity")) {
			throw ProbeException.badRequest("entity", "the entity's id is needed: {\"entity\": n}");
		}
		int id = (int) call.number("entity", 0, Integer.MIN_VALUE, Integer.MAX_VALUE);
		Entity found = world(call).getEntityByID(id);
		if (found == null) {
			throw new ProbeException("NotFound", "no entity " + id + " in the world (gone, or never there)",
				Json.object("what", id));
		}
		return found;
	}

	/** Made by its type, placed and spawned, as today's spawn(); refused where no chunk is loaded (8.8). */
	private static JsonElement spawn(Call call) throws ProbeException {
		String type = call.string("type", null);
		if (type == null) {
			throw ProbeException.badRequest("type", "entity.spawn needs the type");
		}
		JsonElement given = call.args.get("pos");
		if (given == null || !given.isJsonArray() || given.getAsJsonArray().size() != 3) {
			throw ProbeException.badRequest("pos", "pos is [x, y, z]");
		}
		double x = given.getAsJsonArray().get(0).getAsDouble();
		double y = given.getAsJsonArray().get(1).getAsDouble();
		double z = given.getAsJsonArray().get(2).getAsDouble();
		World world = world(call);
		Entity entity = EntityList.createEntityByName(type, world);
		if (entity == null) {
			throw new ProbeException("NotFound", "this game has no entity " + type, Json.object("what", type));
		}
		if (!world.blockExists((int) Math.floor(x), (int) Math.floor(y), (int) Math.floor(z))) {
			throw new ProbeException("NotReady", "no chunk is loaded at " + x + " " + y + " " + z + ": 1.7.10 would drop"
				+ " the " + type + " without a word", Json.object("what", type));
		}
		JsonObject look = call.object("look");
		float yaw = look != null && look.has("yaw") ? look.get("yaw").getAsFloat() : 0.0F;
		float pitch = look != null && look.has("pitch") ? look.get("pitch").getAsFloat() : 0.0F;
		if (call.has("nbt")) {
			// the given data over the entity's own, as /summon's tag does
			net.minecraft.nbt.NBTTagCompound tag = compound(call.string("nbt", null), "nbt");
			net.minecraft.nbt.NBTTagCompound data = new net.minecraft.nbt.NBTTagCompound();
			entity.writeToNBT(data);
			for (Object key : tag.getKeySet()) {
				data.setTag((String) key, tag.getTag((String) key));
			}
			entity.readFromNBT(data);
		}
		entity.setLocationAndAngles(x, y, z, yaw, pitch);
		if (call.flag("initialize", false) && entity instanceof EntityLiving) {
			((EntityLiving) entity).onSpawnWithEgg(null);
		}
		if (!world.spawnEntityInWorld(entity)) {
			throw new ProbeException("NotReady", "the world refused the " + type + " at " + x + " " + y + " " + z, null);
		}
		return Values.entity(entity);
	}

	// ---------------------------------------------------------------- keys and screens

	/** A key binding by its id, or a raw code ({"code": n}). */
	private static int key(Call call) throws ProbeException {
		JsonElement key = call.args.get("key");
		if (key != null && key.isJsonObject() && key.getAsJsonObject().has("code")) {
			return key.getAsJsonObject().get("code").getAsInt();
		}
		if (key == null || !key.isJsonPrimitive()) {
			throw ProbeException.badRequest("key", "key is a binding's id (\"key.jump\") or {\"code\": n}");
		}
		Integer code = Input.bindingCode(Minecraft.getMinecraft(), key.getAsString());
		if (code == null) {
			throw ProbeException.badRequest("key", "this game has no key binding " + key.getAsString());
		}
		return code;
	}

	private static JsonElement tapDown(Call call) throws ProbeException {
		int code = key(call);
		call.mark = code;
		Input.down(code);
		return new JsonObject();
	}

	/** key.tap's rest: the ticks held, then the key let go (also when cancelled meanwhile), then one tick more. */
	private static JsonElement tapUp(Call call, JsonElement value) throws ProbeException, InterruptedException {
		long held = call.number("ticks", 1, 1, 72000);
		int code = (int) call.mark;
		try {
			wait(call, held, value);
		} finally {
			Sides.get().post(Side.CLIENT, () -> {
				Input.up(code);
				return null;
			});
		}
		return wait(call, 1, value);
	}

	private static GuiScreen openScreen(Call call) throws ProbeException {
		GuiScreen screen = Minecraft.getMinecraft().currentScreen;
		if (screen == null) {
			throw new ProbeException("NotReady", "no screen is open to type into", null);
		}
		return screen;
	}

	/** Runs the screen's own keyTyped; what it throws is the screen's failure, a GameError. */
	private static void typed(GuiScreen screen, char character, int code) throws ProbeException {
		try {
			Input.keyTyped(screen, character, code);
		} catch (RuntimeException | Error e) {
			throw new ProbeException("GameError", screen.getClass().getName() + ".keyTyped threw " + e, Json.object(
				"exception", e.getClass().getName(), "trace", Probe.trace(e)));
		}
	}

	private static JsonElement type(Call call) throws ProbeException {
		GuiScreen screen = openScreen(call);
		String text = call.string("text", null);
		if (text == null) {
			throw ProbeException.badRequest("text", "screen.type needs the text");
		}
		for (char character : text.toCharArray()) {
			typed(screen, character, 0);
		}
		return new JsonObject();
	}

	private static JsonElement screenKey(Call call) throws ProbeException {
		GuiScreen screen = openScreen(call);
		String name = call.string("key", null);
		int[] key = name == null ? null : Input.portableKey(name);
		if (key == null) {
			throw ProbeException.badRequest("key", "key is a letter, a digit, space, enter, escape, tab, backspace, delete,"
				+ " up, down, left, right, home, end, page_up, page_down or f1 to f12, not " + name);
		}
		typed(screen, (char) key[1], key[0]);
		return new JsonObject();
	}

	private static JsonElement chatRead(Call call) throws ProbeException {
		GuiScreen screen = Minecraft.getMinecraft().currentScreen;
		if (!(screen instanceof GuiChat)) {
			throw new ProbeException("NotReady", "the chat isn't open (the screen is "
				+ (screen == null ? "none" : screen.getClass().getName()) + ")", null);
		}
		JsonArray suggestions = new JsonArray();
		for (String each : ChatScreen.suggestions(screen)) {
			suggestions.add(Json.of(each));
		}
		JsonArray usage = new JsonArray();
		for (String each : ChatScreen.usage(screen)) {
			usage.add(Json.of(each));
		}
		return Json.object("text", ChatScreen.text(screen), "suggestions", suggestions, "usage", usage);
	}

	/** As if typed into the chat and sent: through the network, into the chat's history (8.6). */
	private static JsonElement chatSend(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getMinecraft();
		String text = call.string("text", null);
		if (text == null) {
			throw ProbeException.badRequest("text", "chat.send needs the text");
		}
		if (mc.thePlayer == null) {
			throw new ProbeException("NotReady", "chat.send needs a world", null);
		}
		call.mark = call.probe.chat.mark();
		mc.ingameGUI.getChatGUI().addToSentMessages(text);
		mc.thePlayer.sendChatMessage(text);
		return Json.object("lines", new JsonArray(), "errors", new JsonArray());
	}

	private static JsonElement chatLines(Call call, JsonElement value) throws ProbeException, InterruptedException {
		wait(call, call.number("settle_ticks", 4, 0, 1200), value);
		JsonArray lines = new JsonArray();
		JsonArray errors = new JsonArray();
		for (JsonObject line : call.probe.chat.since(call.mark)) {
			lines.add(line.get("plain"));
			if (Json.string(line, "formatted").startsWith("§c")) {
				errors.add(line.get("plain"));
			}
		}
		return Json.object("lines", lines, "errors", errors);
	}

	private static JsonElement camera(Call call) throws ProbeException {
		long view = call.number("view", -1, 0, 2);
		if (view < 0) {
			throw ProbeException.badRequest("view", "camera.set needs the view: 0, 1 or 2");
		}
		Input.camera(Minecraft.getMinecraft(), (int) view);
		return new JsonObject();
	}

	private static JsonElement sound(Call call) throws ProbeException {
		String id = call.string("id", null);
		if (id == null) {
			throw ProbeException.badRequest("id", "sound.play needs the sound's id");
		}
		float pitch = call.has("pitch") ? call.args.get("pitch").getAsFloat() : 1.0F;
		Minecraft.getMinecraft().getSoundHandler().playSound(
			PositionedSoundRecord.createPositionedSoundRecord(new ResourceLocation(id), pitch));
		return new JsonObject();
	}

	// ---------------------------------------------------------------- pictures

	private static JsonElement screenshotBefore(Call call) throws ProbeException {
		String file = call.string("file", null);
		if (file == null || !new File(file).isAbsolute()) {
			throw ProbeException.badRequest("file", "screenshot needs the file to write, an absolute path");
		}
		if (call.flag("clear_chat", true)) {
			Pictures.clearChat(Minecraft.getMinecraft());
		}
		return new JsonObject();
	}

	/** After the chat is cleared, the ticks for the frame to show it all, then the picture, on the client thread. */
	private static JsonElement screenshotTake(Call call, JsonElement value) throws ProbeException, InterruptedException {
		wait(call, call.number("settle_ticks", 2, 0, 1200), value);
		File file = new File(call.string("file", null));
		try {
			return Sides.get().run(Side.CLIENT, () -> {
				Minecraft mc = Minecraft.getMinecraft();
				Pictures.saveAs(mc, file);
				return Json.object("file", file.getAbsolutePath(), "width", mc.displayWidth, "height", mc.displayHeight);
			}, Sides.STALL_SECONDS, null);
		} catch (InterruptedException | RuntimeException e) {
			throw e;
		} catch (IOException e) {
			throw new ProbeException("ProbeError", "the picture couldn't be written: " + e, null);
		} catch (Exception e) {
			throw new ProbeException("ProbeError", "the picture failed: " + e, null);
		}
	}
}
