package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.mixins.fabric.MinecraftAccess;
import io.github.asgerjon.unittas.mixins.fabric.TrapDoorBlockAccess;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.BlockTags;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.FenceGateBlock;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.phys.shapes.CollisionContext;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * player.perceive (PROTOCOL.md 8.4; SPEC.md 15.6 step 1, 19.7 step 3) in 26.3, as 1.7.10's Perceive: what the client's
 * player perceives now, for the agent's brain in Python. Where it stands and how it moves, its own collision box, what
 * its crosshair targets by the game's own pick (made afresh, Minecraft.pick), its reach, and the blocks around it as
 * the game collides with them, each by its id and state (26.3 has no meta). The probe says what is there; it decides
 * nothing. block.ground too: the column's top block that stops movement or holds a fluid (MOTION_BLOCKING).
 */
final class FabricPerceive {

	private FabricPerceive() {
	}

	static void bind(Probe probe) {
		probe.op("player.perceive").does(FabricPerceive::perceive);
		probe.op("block.ground").does(FabricPerceive::ground);
	}

	private static JsonElement perceive(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		LocalPlayer player = mc.player;
		ClientLevel level = mc.level;
		if (player == null || level == null) {
			throw new ProbeException("NotReady", "player.perceive needs a world", null);
		}
		int around = (int) call.number("around", 2, 0, 8);
		// how far below the feet's block and above the head's it looks, in blocks (terrain: SPEC.md 15.6 step 7)
		int below = (int) call.number("below", 1, 0, 8);
		int above = (int) call.number("above", 1, 0, 8);
		// the game's own pick, as each tick makes it, for the look as it is now
		((MinecraftAccess) mc).unittas$pick(1.0F);
		Entity camera = mc.getCameraEntity() == null ? player : mc.getCameraEntity();
		Vec3 eye = camera.getEyePosition(1.0F);
		Vec3 motion = player.getDeltaMovement();
		return Json.object(
			"tick", Sides.get().ticks(Side.CLIENT),
			"pos", FabricValues.pos(player),
			"eye", Arrays.asList(eye.x, eye.y, eye.z),
			"box", box(player.getBoundingBox()),
			"look", FabricValues.look(player),
			"motion", Arrays.asList(motion.x, motion.y, motion.z),
			"on_ground", player.onGround(),
			"collided", Json.object("horizontally", player.horizontalCollision, "vertically", player.verticalCollision),
			"in_water", player.isInWater(),
			"in_lava", player.isInLava(),
			"on_ladder", player.onClimbable(),
			"sneaking", player.isShiftKeyDown(),
			"sprinting", player.isSprinting(),
			"flying", player.getAbilities().flying,
			"reach", Json.object("block", player.blockInteractionRange(), "entity", player.entityInteractionRange()),
			"target", target(level, mc.hitResult),
			"blocks", around(level, player, around, below, above));
	}

	/**
	 * Whether a hand's click opens and shuts it: a door or trapdoor whose kind a hand opens (wooden, copper; not iron),
	 * a fence gate.
	 */
	private static boolean opens(Block block) {
		if (block instanceof DoorBlock door) {
			return door.type().canOpenByHand();
		}
		if (block instanceof TrapDoorBlock) {
			return ((TrapDoorBlockAccess) block).unittas$type().canOpenByHand();
		}
		return block instanceof FenceGateBlock;
	}

	private static List<Double> box(AABB box) {
		return Arrays.asList(box.minX, box.minY, box.minZ, box.maxX, box.maxY, box.maxZ);
	}

	/** The crosshair's target, in player.use's shape (8.4) with what was hit; null when nothing is within reach. */
	private static JsonElement target(Level level, HitResult hit) {
		if (hit == null || hit.getType() == HitResult.Type.MISS) {
			return null;
		}
		Vec3 at = hit.getLocation();
		List<Double> where = Arrays.asList(at.x, at.y, at.z);
		if (hit instanceof EntityHitResult entity) {
			return Json.object("entity", entity.getEntity().getId(), "type", FabricValues.type(entity.getEntity()),
				"hit", where);
		}
		BlockHitResult block = (BlockHitResult) hit;
		BlockPos pos = block.getBlockPos();
		JsonObject value = Json.object(
			"block", Arrays.asList(pos.getX(), pos.getY(), pos.getZ()),
			"face", block.getDirection().getName(),
			"hit", where);
		// its id and state, as block.get gives them
		FabricValues.block(level.getBlockState(pos)).entrySet().forEach(each -> value.add(each.getKey(), each.getValue()));
		return value;
	}

	/**
	 * The blocks that aren't air within 'reach' blocks of the feet's block across, from 'below' blocks below the feet's
	 * block to 'above' blocks above the head's: each by its id and state, with its collision boxes as the game gives them
	 * for this player (none for a flower), whether it is a liquid, whether the player can climb it, and whether a hand's
	 * click opens it.
	 */
	private static List<Object> around(Level level, LocalPlayer player, int reach, int below, int above) {
		List<Object> found = new ArrayList<>();
		int feetX = Mth.floor(player.getX());
		int feetY = Mth.floor(player.getBoundingBox().minY);
		int feetZ = Mth.floor(player.getZ());
		CollisionContext context = CollisionContext.of(player);
		for (int y = feetY - below; y <= feetY + 1 + above; y++) {
			for (int x = feetX - reach; x <= feetX + reach; x++) {
				for (int z = feetZ - reach; z <= feetZ + reach; z++) {
					BlockPos pos = new BlockPos(x, y, z);
					BlockState state = level.getBlockState(pos);
					if (state.isAir()) {
						continue;
					}
					JsonArray boxes = new JsonArray();
					for (AABB box : state.getCollisionShape(level, pos, context).toAabbs()) {
						JsonArray each = new JsonArray();
						box(box.move(pos)).forEach(each::add);
						boxes.add(each);
					}
					JsonObject block = Json.object("pos", Arrays.asList(x, y, z));
					FabricValues.block(state).entrySet().forEach(each -> block.add(each.getKey(), each.getValue()));
					block.add("boxes", boxes);
					block.addProperty("liquid", state.liquid());
					block.addProperty("climbable", state.is(BlockTags.CLIMBABLE));
					block.addProperty("opens", opens(state.getBlock()));
					found.add(block);
				}
			}
		}
		return found;
	}

	/**
	 * block.ground (8.4): the top block of the column at x, z that stops movement or holds a fluid (the game's own
	 * MOTION_BLOCKING height map: leaves and water count, tall grass and flowers don't), on the call's side; NotFound
	 * where nothing in the column does.
	 */
	private static JsonElement ground(Call call) throws ProbeException {
		if (!call.has("x") || !call.has("z")) {
			throw ProbeException.badRequest("x", "x and z are the column's whole numbers");
		}
		int x = (int) call.number("x", 0, -30000000, 30000000);
		int z = (int) call.number("z", 0, -30000000, 30000000);
		Level level = FabricThings.player(call).level();
		int top = level.getHeight(Heightmap.Types.MOTION_BLOCKING, x, z) - 1;
		if (top < level.getMinY()) {
			throw new ProbeException("NotFound", "nothing at x " + x + ", z " + z + " stops movement or holds a fluid",
				Json.object("what", "the ground at x " + x + ", z " + z));
		}
		BlockPos pos = new BlockPos(x, top, z);
		return Json.object("pos", Arrays.asList(x, top, z), "block", FabricValues.block(level.getBlockState(pos)));
	}
}
