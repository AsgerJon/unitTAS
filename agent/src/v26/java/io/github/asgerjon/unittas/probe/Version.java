package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.InputConstants;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import com.mojang.serialization.DataResult;
import com.mojang.serialization.DynamicOps;
import com.mojang.serialization.JsonOps;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.SharedConstants;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.gui.components.ChatComponent;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.input.CharacterEvent;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.client.multiplayer.chat.GuiMessageSource;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.Registry;
import net.minecraft.core.component.DataComponentPatch;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtOps;
import net.minecraft.nbt.Tag;
import net.minecraft.nbt.TagParser;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.ComponentSerialization;
import net.minecraft.network.protocol.game.ClientboundSetHeldSlotPacket;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.util.ProblemReporter;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.minecraft.world.level.portal.TeleportTransition;
import net.minecraft.world.level.storage.TagValueInput;
import net.minecraft.world.level.storage.TagValueOutput;
import net.minecraft.world.phys.Vec3;
import org.lwjgl.sdl.SDLMouse;

import java.util.List;
import java.util.Optional;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

/**
 * What 26.3 does its own way, for the probe's code shared by the versions (agent/src/modern/java; SPEC.md 19.7 step
 * 6c): each version has a Version of its own with these same methods, compiled with the shared code against that
 * version's classes, so a version that lacks one doesn't build. What differs widely (the view, the looks, the worlds)
 * is in the version's own classes instead (V26View, V26Looks, V26Worlds).
 */
final class Version {

	private Version() {
	}

	// ---------------------------------------------------------------- the game

	/** The probe's port, as its hello says it. */
	static String port() {
		return "26.3";
	}

	/** The game's version, as it says itself. */
	static String minecraft() {
		return SharedConstants.getCurrentVersion().name();
	}

	/** The version's own operations, which differ too widely to share: the view and the looks. */
	static void bindOwn(Probe probe) {
		V26View.bind(probe);
		V26Looks.bind(probe);
	}

	/** The version's worlds: the core's WorldOps on its calls. */
	static GameWorlds worlds() {
		return new V26Worlds();
	}

	/** The running world's folder's name; null when none is open. */
	static String worldFolder(MinecraftServer server) {
		return V26Worlds.folder(server);
	}

	/** A chat line's kind from the hooked addMessage's arguments: a player's (chat), or the game's (system). */
	static String chatKind(Object[] arguments) {
		return arguments[2] == GuiMessageSource.PLAYER ? "chat" : "system";
	}

	/** The version's own hooks, which the shared entry passes on: 26.3 has none (its render states keep the frame). */
	static Object hook(String id, Object self, Object[] arguments, Object pass) {
		throw new IllegalArgumentException("the probe knows no hook " + id);
	}

	// ---------------------------------------------------------------- screens and the HUD

	static Screen screen() {
		return Minecraft.getInstance().gui.screen();
	}

	static void setScreen(Screen screen) {
		Minecraft.getInstance().gui.setScreen(screen);
	}

	/** Whether a loading overlay is up (the game's start, a resource reload). */
	static boolean loading() {
		return Minecraft.getInstance().gui.overlay() != null;
	}

	static ChatComponent chat() {
		return Minecraft.getInstance().gui.hud.getChat();
	}

	static boolean hudHidden() {
		return Minecraft.getInstance().gui.hud.isHidden();
	}

	/** The HUD hidden if shown, shown if hidden (F1's). */
	static void toggleHud() {
		Minecraft.getInstance().gui.hud.toggle();
	}

	/** The chat screen, opened with that text in its box. */
	static ChatScreen chatScreen(String text) {
		return new ChatScreen(text, false);
	}

	/** Whether the window holds the pointer (SDL3's relative mouse mode, which the game's grab sets). */
	static boolean pointerGrabbed() {
		Minecraft mc = Minecraft.getInstance();
		return SDLMouse.SDL_GetWindowRelativeMouseMode(mc.getWindow().handle());
	}

	/** The frame as the screen shows it; 26.3 hands it back a frame or two later, on the client thread. */
	static void screenshot(Consumer<NativeImage> taken) {
		Screenshot.takeScreenshot(Minecraft.getInstance().gameRenderer.mainRenderTarget(), taken::accept);
	}

	// ---------------------------------------------------------------- ids

	/** A key's id as text (minecraft:overworld). */
	static String id(ResourceKey<?> key) {
		return key.identifier().toString();
	}

	/** The registry's entry by its id; empty for an id it hasn't, or text that is no id. */
	static <T> Optional<T> byId(Registry<T> registry, String id) {
		Identifier key = Identifier.tryParse(id);
		return key == null ? Optional.empty() : registry.getOptional(key);
	}

	/** Whether the registry has the id (a defaulted one, the blocks', answers its default for any other). */
	static boolean known(Registry<?> registry, String id) {
		Identifier key = Identifier.tryParse(id);
		return key != null && registry.containsKey(key);
	}

	/** A key in the registry by its id; null for text that is no id. */
	static <T> ResourceKey<T> key(ResourceKey<? extends Registry<T>> registry, String id) {
		Identifier key = Identifier.tryParse(id);
		return key == null ? null : ResourceKey.create(registry, key);
	}

	// ---------------------------------------------------------------- sounds

	/** A sound by its id, as a UI sound plays it; null for text that is no id. */
	static SoundEvent soundEvent(String id) {
		Identifier key = Identifier.tryParse(id);
		return key == null ? null : SoundEvent.createVariableRangeEvent(key);
	}

	static String soundId(SoundInstance sound) {
		return sound.getIdentifier().toString();
	}

	/** Whether the game has the sound: resolved as the engine does (getOrResolve, which the engine then reuses). */
	static boolean soundKnown(SoundInstance sound, SoundManager manager) {
		return sound.getOrResolve(manager) != null;
	}

	// ---------------------------------------------------------------- the inventory

	/** The main slots: the hotbar's nine, then the rest. */
	static List<ItemStack> mainItems(Inventory inventory) {
		return inventory.getNonEquipmentItems();
	}

	static int selectedSlot(Inventory inventory) {
		return inventory.getSelectedSlot();
	}

	static void selectSlot(Inventory inventory, int slot) {
		inventory.setSelectedSlot(slot);
	}

	static ItemStack selectedItem(Inventory inventory) {
		return inventory.getSelectedItem();
	}

	/** The game's own pick of what the crosshair meets, made afresh for the look as it is now (Minecraft's, private). */
	static void pick(float partialTick) {
		Members.call(Picking.PICK, Minecraft.getInstance(), partialTick);
	}

	private static final class Picking {

		static final java.lang.reflect.Method PICK = Members.method(Minecraft.class, "pick", float.class);
	}

	// ---------------------------------------------------------------- items' data, chat, reach, results

	/** An item's own data as the protocol has it: its component patch as SNBT ("components"), when it has any. */
	static void itemData(ItemStack stack, HolderLookup.Provider registries, JsonObject item) {
		DataComponentPatch patch = stack.getComponentsPatch();
		if (!patch.isEmpty()) {
			Tag written = DataComponentPatch.CODEC.encodeStart(registries.createSerializationContext(NbtOps.INSTANCE), patch)
				.getOrThrow();
			item.addProperty("components", written.toString());
		}
	}

	/**
	 * The protocol's item's data put on its stack: its components (SNBT of a component patch); BadRequest for nbt, which
	 * 26.3's items haven't (data components from 1.20.5), and for components that aren't the item's.
	 */
	static void applyItemData(ItemStack stack, JsonObject given, String id, HolderLookup.Provider registries)
		throws ProbeException {
		if (given.has("nbt")) {
			throw ProbeException.badRequest("item", port() + "'s items have components, not NBT");
		}
		String components = Json.string(given, "components");
		if (components == null) {
			return;
		}
		DataResult<DataComponentPatch> read = DataComponentPatch.CODEC.parse(
			registries.createSerializationContext(NbtOps.INSTANCE), ModernValues.compound(components, "item"));
		Optional<DataComponentPatch> patch = read.result();
		if (patch.isEmpty()) {
			throw ProbeException.badRequest("item", "the components aren't " + id + "'s: "
				+ read.error().map(DataResult.Error::message).orElse(components));
		}
		stack.applyComponents(patch.get());
	}

	/** A chat line as the game's own JSON, by its registries when a world is open. */
	static String chatJson(Component message) {
		Minecraft mc = Minecraft.getInstance();
		DynamicOps<JsonElement> ops = mc.level == null ? JsonOps.INSTANCE
			: mc.level.registryAccess().createSerializationContext(JsonOps.INSTANCE);
		return ComponentSerialization.CODEC.encodeStart(ops, message).result().map(JsonElement::toString).orElse("");
	}

	/** How far the player reaches a block: its attribute's, as the game's pick takes it. */
	static double blockReach(Player player) {
		return player.blockInteractionRange();
	}

	/** How far the player reaches an entity: its attribute's, as the game's pick takes it. */
	static double entityReach(Player player) {
		return player.entityInteractionRange();
	}

	/** The source, its command's result kept in result[0] as the command ends. */
	static CommandSourceStack withResult(CommandSourceStack source, int[] result) {
		return source.withCallback((success, value) -> result[0] = value);
	}

	/** A block entity's data, without its id and place, as /data reads it. */
	static CompoundTag tileData(BlockEntity tile, HolderLookup.Provider registries) {
		return tile.saveWithoutMetadata(registries);
	}

	/** A mob effect's id (minecraft:speed). */
	static String effectId(MobEffectInstance effect) {
		return effect.getEffect().unwrapKey().map(Version::id).orElse("");
	}

	/** A trapdoor's kind, whose hand-opening it says (its getter protected). */
	static BlockSetType trapdoorType(TrapDoorBlock block) {
		return Members.call(Trapdoors.TYPE, block);
	}

	/** Found at the first trapdoor asked about, once the probe has its names. */
	private static final class Trapdoors {

		static final java.lang.reflect.Method TYPE = Members.method(TrapDoorBlock.class, "getType");
	}

	// ---------------------------------------------------------------- the world, players and entities

	/** The lowest block a level has. */
	static int minY(Level level) {
		return level.getMinY();
	}

	static ServerLevel level(ServerPlayer player) {
		return player.level();
	}

	/** A player to another place, in that level, looking that way, nothing else changed. */
	static void teleport(ServerPlayer player, ServerLevel to, double x, double y, double z, float yaw, float pitch) {
		player.teleport(new TeleportTransition(to, new Vec3(x, y, z), Vec3.ZERO, yaw, pitch,
			TeleportTransition.DO_NOTHING));
	}

	/** No bed or anchor to respawn at. */
	static void clearRespawn(ServerPlayer player) {
		player.setRespawnPosition(null, false);
	}

	/** The held slot told to the player's client. */
	static void sendHeldSlot(ServerPlayer player, int slot) {
		player.connection.send(new ClientboundSetHeldSlotPacket(slot));
	}

	/** An entity's data, without its id, as /data reads it. */
	static CompoundTag save(Entity entity, HolderLookup.Provider registries) {
		TagValueOutput data = TagValueOutput.createWithContext(ProblemReporter.DISCARDING, registries);
		entity.saveWithoutId(data);
		return data.buildResult();
	}

	static void load(Entity entity, CompoundTag data, HolderLookup.Provider registries) {
		entity.load(TagValueInput.create(ProblemReporter.DISCARDING, registries, data));
	}

	static void loadTile(BlockEntity tile, CompoundTag data, HolderLookup.Provider registries) {
		tile.loadWithComponents(TagValueInput.create(ProblemReporter.DISCARDING, registries, data));
	}

	/** An entity made as a command makes one; null for a kind a command can't make. */
	static Entity create(EntityType<?> kind, ServerLevel level) {
		return kind.create(level, EntitySpawnReason.COMMAND);
	}

	/** A mob given what it would have spawned with, as /summon does. */
	static void finalizeSpawn(Mob mob, ServerLevel level) {
		mob.finalizeSpawn(level, level.getCurrentDifficultyAt(mob.blockPosition()), EntitySpawnReason.COMMAND, null);
	}

	/** An entity put at a place, looking that way, before it is in a world. */
	static void place(Entity entity, double x, double y, double z, float yaw, float pitch) {
		entity.snapTo(x, y, z, yaw, pitch);
	}

	/** A block's state from text, as commands read it (minecraft:oak_stairs[facing=east]). */
	static BlockState parseBlock(String text) throws CommandSyntaxException {
		return BlockStateParser.parseForBlock(BuiltInRegistries.BLOCK, text, false).blockState();
	}

	/** A compound from SNBT, as the game's own commands read it. */
	static CompoundTag parseCompound(String text) throws CommandSyntaxException {
		return TagParser.parseCompoundFully(text);
	}

	/** Each of a state's properties, by its name and its value's name. */
	static void properties(BlockState state, BiConsumer<String, String> each) {
		state.getValues().forEach(value -> each.accept(value.property().getName(), value.valueName()));
	}

	// ---------------------------------------------------------------- input

	/** A raw key by its code: SDL3's scancode. */
	static InputConstants.Key rawKey(int code) {
		return InputConstants.Type.KEYBOARD.getOrCreate(code);
	}

	/** A binding by its name (key.jump); null for none. */
	static KeyMapping binding(String name) {
		return KeyMapping.get(name);
	}

	/** A screen given a character, as SDL3 gives one. */
	static void charTyped(Screen screen, int character) {
		screen.charTyped(new CharacterEvent(character));
	}

	/** A screen given a key, as SDL3 gives one: its scancode and its keycode. */
	static void keyPressed(Screen screen, int scancode, int keycode) {
		screen.keyPressed(new KeyEvent(scancode, keycode, 0));
	}

	/**
	 * A key by its portable name, as a screen is given it: [its scancode, its keycode (SDL3's: the character for a
	 * key that types one, the scancode with bit 30 for the rest), the character it types or 0]; null for a name not
	 * known.
	 */
	static int[] portableKey(String name) {
		if (name.length() == 1) {
			char c = name.charAt(0);
			if (c >= 'a' && c <= 'z') {
				return new int[] {InputConstants.KEY_A + (c - 'a'), c, c};
			}
			if (c >= '1' && c <= '9') {
				return new int[] {InputConstants.KEY_1 + (c - '1'), c, c};
			}
			if (c == '0') {
				return new int[] {InputConstants.KEY_0, c, c};
			}
			return null;
		}
		switch (name) {
			case "space": return new int[] {InputConstants.KEY_SPACE, ' ', ' '};
			case "enter": return new int[] {InputConstants.KEY_RETURN, '\r', 0};
			case "escape": return new int[] {InputConstants.KEY_ESCAPE, 27, 0};
			case "tab": return new int[] {InputConstants.KEY_TAB, '\t', 0};
			case "backspace": return new int[] {InputConstants.KEY_BACKSPACE, '\b', 0};
			case "delete": return new int[] {InputConstants.KEY_DELETE, 127, 0};
			case "up": return new int[] {InputConstants.KEY_UP, sdl(InputConstants.KEY_UP), 0};
			case "down": return new int[] {InputConstants.KEY_DOWN, sdl(InputConstants.KEY_DOWN), 0};
			case "left": return new int[] {InputConstants.KEY_LEFT, sdl(InputConstants.KEY_LEFT), 0};
			case "right": return new int[] {InputConstants.KEY_RIGHT, sdl(InputConstants.KEY_RIGHT), 0};
			case "home": return new int[] {InputConstants.KEY_HOME, sdl(InputConstants.KEY_HOME), 0};
			case "end": return new int[] {InputConstants.KEY_END, sdl(InputConstants.KEY_END), 0};
			case "page_up": return new int[] {InputConstants.KEY_PAGEUP, sdl(InputConstants.KEY_PAGEUP), 0};
			case "page_down": return new int[] {InputConstants.KEY_PAGEDOWN, sdl(InputConstants.KEY_PAGEDOWN), 0};
			default:
				break;
		}
		if (name.matches("f([1-9]|1[0-2])")) {
			int scancode = InputConstants.KEY_F1 + Integer.parseInt(name.substring(1)) - 1;
			return new int[] {scancode, sdl(scancode), 0};
		}
		return null;
	}

	/** SDL3's keycode for a key that types nothing: its scancode with bit 30 (SDLK_SCANCODE_MASK). */
	private static int sdl(int scancode) {
		return scancode | (1 << 30);
	}

	// ---------------------------------------------------------------- containers

	/** container.click's modes, in 1.7.10's order (pickup, quick_move, swap, clone, throw, quick_craft, pickup_all). */
	static Object[] clickModes() {
		return ContainerInput.values();
	}

	/** The class of a click's mode, for the screen's own slotClicked. */
	static Class<?> clickModeClass() {
		return ContainerInput.class;
	}

	/** The file a crash report was saved to, or null where it couldn't be (its save file is a Path here). */
	static java.io.File crashFile(net.minecraft.CrashReport report) {
		java.nio.file.Path saved = report.getSaveFile();
		return saved == null ? null : saved.toFile();
	}
}
